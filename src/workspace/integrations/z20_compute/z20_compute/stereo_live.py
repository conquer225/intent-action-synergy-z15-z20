"""Latest paired snapshot from passive write descriptors; video is never controlled."""
from dataclasses import dataclass, field, replace
import time
import mmap
import os
import struct
from pathlib import Path
import numpy as np
from .video import FrameSnapshot


@dataclass(frozen=True)
class CameraState:
    writer_index: int
    completed_index: int
    write_epoch: int
    completed_sequence: int
    writer_valid: bool
    completed_valid: bool
    fault: bool


@dataclass(frozen=True)
class StereoState:
    revision: int
    cameras: tuple
    captured_ns: int = field(compare=False)
    age_ns: int = field(compare=False)
    pair_skew_ns: object = field(default=None,compare=False)


class StereoSnapshotReader:
    def __init__(self, state, copy_frame, *, max_age_ns=2_000_000_000, independent_slots=False,
                 max_pair_skew_ns=None):
        self.state, self.copy_frame = state, copy_frame
        self.max_age_ns = max_age_ns
        self.independent_slots = independent_slots
        self.last_sequence = -1
        if max_pair_skew_ns is not None and (not independent_slots or type(max_pair_skew_ns) is not int or not 0<max_pair_skew_ns<=5_000_000):
            raise ValueError('timestamp pairing requires independent slots and a 0..5ms completion limit')
        self.max_pair_skew_ns=max_pair_skew_ns
        self.last_sequences=(-1,-1);self.last_pair_skew_ns=None

    def latest(self):
        before = self.state()
        a, b = before.cameras
        if a.fault or b.fault:
            raise RuntimeError('video write observer fault; inspect VDMA status before restarting PL')
        for cam in (a, b):
            if not (cam.writer_valid and cam.completed_valid):
                return None
            if not (0 <= cam.writer_index < 3 and 0 <= cam.completed_index < 3):
                raise ValueError('video descriptor index outside three-frame ring')
        slots = tuple(cam.completed_index for cam in before.cameras)
        sequences=tuple(cam.completed_sequence for cam in before.cameras)
        if self.max_pair_skew_ns is None:
            paired=a.completed_sequence==b.completed_sequence and a.completed_sequence>self.last_sequence
        else:
            paired=(before.pair_skew_ns is not None and 0<=before.pair_skew_ns<=self.max_pair_skew_ns
                and all(new>old for new,old in zip(sequences,self.last_sequences)))
        if ((not self.independent_slots and a.completed_index != b.completed_index)
                or not paired
                or any(cam.writer_index == slot for cam, slot in zip(before.cameras, slots))
                or before.age_ns > self.max_age_ns):
            return None
        pixels = np.array(self.copy_frame(slots if self.independent_slots else slots[0]), copy=True)
        after = self.state()
        # One new frame can start in another slot during a copy. Two or more
        # starts could have visited the copied slot even if the final index
        # looks safe (ABA), so discard those conservatively.
        safe = all(new.writer_valid and new.completed_valid and not new.fault
                   and new.writer_index != slot
                   and new.completed_sequence >= old.completed_sequence
                   and ((new.write_epoch-old.write_epoch) & 0xffffffff) <= 1
                   for old, new, slot in zip(before.cameras, after.cameras, slots))
        if not safe or before.age_ns > self.max_age_ns or after.age_ns > self.max_age_ns:
            return None
        pixels.flags.writeable = False
        self.last_sequence=max(sequences);self.last_sequences=sequences;self.last_pair_skew_ns=before.pair_skew_ns
        return FrameSnapshot(self.last_sequence, before.captured_ns, pixels)


class ObserverRegisters:
    """Decode a coherent descriptor. read_word is an ordered device-MMIO read."""
    def __init__(self, read_word, *, now_ns=time.monotonic_ns):
        self.read, self.now_ns = read_word, now_ns
        expected = {0: 0x5a325643, 4: 1, 0x0c: 142857132, 0x40: 0x01000000,
                    0x44: 2764800, 0x48: 3840, 0x4c: 720, 0x50: 1920}
        if any(self.read(offset) != value for offset, value in expected.items()):
            raise ValueError('observer ID/version/geometry/clock does not match this capture adapter')

    def _counter(self, offset):
        for _ in range(8):
            high = self.read(offset+4)
            low = self.read(offset)
            if high == self.read(offset+4):
                return (high << 32) | low
        raise RuntimeError('unstable hardware time counter')

    def state(self):
        for _ in range(8):
            # Timestamp before reading PL time conservatively overestimates age.
            now_ns = self.now_ns()
            revision = self.read(8)
            cameras = []
            for offset in (0x10, 0x1c):
                flags = self.read(offset)
                cameras.append(CameraState((flags >> 8) & 3, (flags >> 10) & 3,
                    self.read(offset+4), self.read(offset+8), bool(flags & 1),
                    bool(flags & 2), bool(flags & 4)))
            completions=(self._counter(0x30),self._counter(0x38))
            completed = min(completions)
            ticks = self._counter(0x28)
            if revision == self.read(8):
                age = (ticks-completed)*1_000_000_000 // 142857132
                if age < 0:
                    raise RuntimeError('observer clock moved backwards')
                skew=abs(completions[0]-completions[1])*1_000_000_000//142857132
                return StereoState(revision, tuple(cameras), max(0, now_ns-age), age,skew)
        raise RuntimeError('video descriptors changed during bounded MMIO read')


class StereoUIO:
    """Read-only UIO map0 descriptors + map1 reserved, uncached frame ring.

    The matching device tree reserves this DDR range before Linux boots. No DMA
    configuration/reset, interrupt control or /dev/mem access is provided.
    """
    def __init__(self, device, maps, *, independent_slots=False, sample_step=(1,1),max_pair_skew_ns=None,camera_index=None):
        if camera_index is not None and (type(camera_index) is not int or camera_index not in (0,1)):
            raise ValueError('single camera index must be 0 or 1')
        if camera_index is not None and max_pair_skew_ns is not None:
            raise ValueError('single camera input has no stereo pairing constraint')
        self.camera_index=camera_index
        if (not isinstance(sample_step, (tuple,list)) or len(sample_step)!=2
                or any(type(v) is not int or v<=0 for v in sample_step)
                or 720%sample_step[0] or 640%sample_step[1]):
            raise ValueError('sample steps must divide camera height and width')
        self.sample_step = sample_step
        self.fd = None
        self.regs = self.frames = None
        maps = Path(maps)
        def number(index, key):
            return int((maps/('map'+str(index))/key).read_text().strip(), 0)
        for index, address, size in [(0, 0x43c20000, 0x1000), (1, 0x01000000, 8294400)]:
            actual = number(index, 'size')
            if (number(index, 'addr') != address or number(index, 'offset') != 0
                    or actual < size or actual > (0x10000 if index == 0 else 8294400)):
                raise ValueError('UIO map does not match observer/reserved frame ring')
        try:
            self.fd = os.open(device, os.O_RDONLY)
            if os.name == 'posix':
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.regs = mmap.mmap(self.fd, number(0, 'size'), access=mmap.ACCESS_READ)
            # Windows mapped-file fixtures require 64 KiB mapping alignment;
            # Linux UIO uses its 4 KiB page offset to select map1.
            map_offset = mmap.PAGESIZE // mmap.ALLOCATIONGRANULARITY * mmap.ALLOCATIONGRANULARITY
            self.frame_view_offset = mmap.PAGESIZE-map_offset
            self.frames = mmap.mmap(self.fd, 8294400+self.frame_view_offset,
                                    access=mmap.ACCESS_READ, offset=map_offset)
            descriptor = ObserverRegisters(lambda offset: struct.unpack_from('<I', self.regs, offset)[0])
            if camera_index is None:
                self.reader = StereoSnapshotReader(descriptor.state,
                    self._frame_pair if independent_slots else self._sampled_frame,
                    independent_slots=independent_slots,max_pair_skew_ns=max_pair_skew_ns)
            else:
                # Reuse the exact completed-slot/ABA fence for one camera.
                # Aggregate capture age remains a conservative bound. Neither
                # the other camera's phase nor its flags define this input.
                def selected():
                    state=descriptor.state();camera=state.cameras[camera_index]
                    return replace(state,cameras=(camera,camera),pair_skew_ns=None)
                self.reader=StereoSnapshotReader(selected,self._camera_frame)
        except BaseException:
            self.close()
            raise

    def _frame_view(self, index):
        return np.ndarray((720, 1280, 3), dtype=np.uint8, buffer=self.frames,
                          offset=self.frame_view_offset+index*2764800)

    def _frame_pair(self, slots):
        # Each writer owns only its half of each ring slot. Reads of the other
        # half cannot race this writer; fence each selected half independently.
        sy,sx = self.sample_step
        return np.concatenate((self._frame_view(slots[0])[::sy, :640:sx],
                               self._frame_view(slots[1])[::sy, 640::sx]), axis=1)

    def _camera_frame(self,index):
        sy,sx=self.sample_step;left=self.camera_index*640
        return self._frame_view(index)[::sy,left:left+640:sx]

    def _sampled_frame(self, index):
        sy,sx = self.sample_step
        return self._frame_view(index)[::sy,::sx]

    def latest(self):
        return self.reader.latest()

    def close(self):
        for name in ('frames', 'regs'):
            mapping = getattr(self, name)
            if mapping is not None:
                mapping.close()
                setattr(self, name, None)
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
