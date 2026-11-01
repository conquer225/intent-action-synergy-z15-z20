import unittest
import tempfile
import struct
from pathlib import Path
from dataclasses import replace
import numpy as np
from z20_compute.stereo_live import CameraState, StereoState, StereoSnapshotReader, ObserverRegisters, StereoUIO


class StereoLiveTests(unittest.TestCase):
    def test_timestamp_pairing_accepts_counter_offset_but_rejects_completion_gap_and_reuse(self):
        left=CameraState(1,0,101,100,True,True,False)
        right=CameraState(0,2,100,99,True,True,False)
        state=StereoState(1,(left,right),1234,0,pair_skew_ns=300000)
        current=[state];copied=[]
        reader=StereoSnapshotReader(lambda:current[0],lambda slots:copied.append(slots) or np.zeros((2,4,3),np.uint8),
            independent_slots=True,max_pair_skew_ns=5_000_000)
        self.assertEqual(reader.latest().sequence,100)
        self.assertIsNone(reader.latest())
        self.assertEqual(copied,[(0,2)])
        current[0]=replace(state,cameras=(replace(left,completed_sequence=101),right))
        self.assertIsNone(reader.latest())
        current[0]=replace(state,pair_skew_ns=6_000_000)
        self.assertIsNone(StereoSnapshotReader(lambda:current[0],lambda _:self.fail('unsafe pair'),
            independent_slots=True,max_pair_skew_ns=5_000_000).latest())

    def test_independent_slots_pair_same_sequence_and_check_each_written_half(self):
        left = CameraState(0, 2, 8, 7, True, True, False)
        right = CameraState(2, 1, 8, 7, True, True, False)
        state = StereoState(3, (left, right), 1234, 0)
        seen = []
        def copy(slots):
            seen.append(slots)
            return np.full((2, 4, 3), 17, np.uint8)
        frame = StereoSnapshotReader(lambda: state, copy, independent_slots=True).latest()
        self.assertEqual(seen, [(2, 1)])
        self.assertEqual(frame.sequence, 7)
        self.assertFalse(frame.pixels.flags.writeable)
        unsafe = replace(state, cameras=(replace(left, writer_index=2), right))
        self.assertIsNone(StereoSnapshotReader(lambda: unsafe, copy, independent_slots=True).latest())

        states = [state]
        def overwritten(slots):
            states[0] = replace(state, cameras=(left, replace(right, writer_index=1, write_epoch=9)))
            return copy(slots)
        self.assertIsNone(StereoSnapshotReader(lambda: states[0], overwritten,
                                               independent_slots=True).latest())

    def test_linux_independent_slot_mapping_assembles_only_the_selected_halves(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); device = root/'uio0'
            with device.open('wb') as f: f.truncate(4096+8294400)
            for index, address, size in [(0, 0x43c20000, 4096), (1, 0x01000000, 8294400)]:
                info = root/('map'+str(index)); info.mkdir()
                for name, value in [('addr', address), ('size', size), ('offset', 0)]:
                    (info/name).write_text(hex(value))
            words = {0: 0x5a325643, 4: 1, 8: 7, 0xc: 142857132,
                     0x40: 0x01000000, 0x44: 2764800, 0x48: 3840, 0x4c: 720, 0x50: 1920,
                     0x10: 0x803, 0x14: 8, 0x18: 7, 0x1c: 0x603, 0x20: 8, 0x24: 7}
            with device.open('r+b') as f:
                for offset, value in words.items(): f.seek(offset); f.write(struct.pack('<I',value))
                f.seek(4096+2*2764800); f.write(b'\x01\x02\x03')
                f.seek(4096+2764800+1920); f.write(b'\x04\x05\x06')
            with StereoUIO(device, root, independent_slots=True) as capture:
                frame = capture.latest()
                np.testing.assert_array_equal(frame.pixels[0,0], [1,2,3])
                np.testing.assert_array_equal(frame.pixels[0,640], [4,5,6])
            with StereoUIO(device, root, independent_slots=True, sample_step=(3,2)) as capture:
                frame = capture.latest()
                self.assertEqual(frame.pixels.shape,(240,640,3))
                np.testing.assert_array_equal(frame.pixels[0,320],[4,5,6])

    def test_copy_survives_unrelated_next_slot_write_without_blocking_video(self):
        cam = CameraState(1, 0, 2, 1, True, True, False)
        current = [StereoState(1, (cam, cam), 100, 0)]
        def copy(index):
            advanced = replace(cam, writer_index=2, write_epoch=3, completed_index=1, completed_sequence=2)
            current[0] = StereoState(4, (advanced, advanced), 200, 0)
            return np.zeros((2,4,3), np.uint8)
        frame = StereoSnapshotReader(lambda: current[0], copy).latest()
        self.assertIsNotNone(frame)
        self.assertEqual((frame.sequence, frame.captured_ns), (1,100))

    def test_linux_mapping_is_readonly_and_checks_reserved_framebuffer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = root/'uio0'
            with device.open('wb') as f: f.truncate(4096+8294400)
            for index, address, size in [(0, 0x43c20000, 4096), (1, 0x01000000, 8294400)]:
                info = root/('map'+str(index));info.mkdir()
                for name, value in [('addr', address), ('size', size), ('offset', 0)]:
                    (info/name).write_text(hex(value))
            words = {0: 0x5a325643, 4: 1, 8: 7, 0xc: 142857132,
                     0x40: 0x01000000, 0x44: 2764800, 0x48: 3840, 0x4c: 720, 0x50: 1920,
                     0x10: 0x103, 0x14: 2, 0x18: 1, 0x1c: 0x103, 0x20: 2, 0x24: 1}
            with device.open('r+b') as f:
                for offset, value in words.items(): f.seek(offset);f.write(struct.pack('<I', value))
                f.seek(4096);f.write(b'\x07\x08\x09')
            with StereoUIO(device, root) as capture:
                frame = capture.latest()
                self.assertEqual(frame.pixels.shape, (720, 1280, 3))
                np.testing.assert_array_equal(frame.pixels[0,0], [7,8,9])
                self.assertFalse(frame.pixels.flags.writeable)
            (root/'map1/addr').write_text('0x02000000')
            with self.assertRaises(ValueError): StereoUIO(device, root)

    def test_descriptor_decodes_both_cameras_and_capture_age(self):
        words = {0: 0x5a325643, 4: 1, 8: 7, 0x0c: 142857132,
                 0x40: 0x01000000, 0x44: 2764800, 0x48: 3840, 0x4c: 720, 0x50: 1920,
                 0x10: 0x103, 0x14: 2, 0x18: 1, 0x1c: 0x103, 0x20: 2, 0x24: 1,
                 0x28: 142857132, 0x2c: 0, 0x30: 71428566, 0x34: 0,
                 0x38: 71428567, 0x3c: 0}
        state = ObserverRegisters(words.__getitem__, now_ns=lambda: 2_000_000_000).state()
        self.assertEqual((state.age_ns, state.captured_ns), (500_000_000, 1_500_000_000))
        self.assertEqual(state.cameras[1], CameraState(1, 0, 2, 1, True, True, False))
        words[0] = 0
        with self.assertRaises(ValueError): ObserverRegisters(words.__getitem__)

    def test_pair_requires_both_writers_clear_and_discards_aba_during_copy(self):
        camera = CameraState(1, 0, 2, 1, True, True, False)
        current = StereoState(3, (camera, camera), 1234, 0)
        states = [current]
        copies = []
        def copy(index):
            copies.append(index)
            return np.zeros((2, 4, 3), np.uint8)
        reader = StereoSnapshotReader(lambda: states[0], copy)
        result = reader.latest()
        self.assertEqual((result.sequence, result.captured_ns), (1, 1234))
        self.assertFalse(result.pixels.flags.writeable)
        self.assertIsNone(reader.latest())
        unsafe = replace(camera, writer_index=0)
        states[0] = replace(current, cameras=(camera, unsafe), revision=4)
        self.assertIsNone(StereoSnapshotReader(lambda: states[0], copy).latest())
        self.assertEqual(copies, [0])
        states[0] = current
        def lapped(index):
            states[0] = replace(current, revision=9, cameras=(replace(camera, write_epoch=5), camera))
            return copy(index)
        self.assertIsNone(StereoSnapshotReader(lambda: states[0], lapped).latest())

    def test_fault_mismatched_pair_and_stale_capture_are_rejected(self):
        cam = CameraState(1, 0, 2, 1, True, True, False)
        def check(state):
            return StereoSnapshotReader(lambda: state, lambda _: self.fail('unsafe copy')).latest()
        self.assertIsNone(check(StereoState(1, (cam, replace(cam, completed_sequence=2)), 1, 0)))
        self.assertIsNone(check(StereoState(1, (cam, cam), 1, 3_000_000_000)))
        with self.assertRaises(RuntimeError):
            check(StereoState(1, (cam, replace(cam, fault=True)), 1, 0))


if __name__ == '__main__': unittest.main()
