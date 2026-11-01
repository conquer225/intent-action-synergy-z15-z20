"""Linux owns all DMA memory via PYNQ CMA; never map bare-metal fixed DDR slots."""
import ctypes as C
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def verify_runtime():
    manifest = json.loads((ROOT / "linux/runtime/manifest.json").read_text(encoding="utf-8"))
    library = ROOT / "linux/runtime/libeye_board.so"
    if hashlib.sha256(library.read_bytes()).hexdigest() != manifest["library_sha256"]:
        raise RuntimeError("Linux runtime hash mismatch")
    for name, digest in manifest["sources"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError("Rebuild Linux runtime after source change: " + name)
    return library
class Video:
    def __init__(self, core):
        from pynq import Overlay, allocate
        import numpy as np
        self.lib = core.lib
        self.buffers = []
        self.opened = False
        self.overlay = None
        self.lib.linux_video_init.argtypes = [C.c_void_p, C.c_void_p]
        self.lib.linux_hw_close.restype = C.c_int
        self.lib.linux_osd_publish.argtypes = [C.c_uint32, C.c_uint32]
        for name in ("live_osd_camera_frames", "live_osd_display_frames", "video_rx_status", "video_tx_status"):
            getattr(self.lib, name).restype = C.c_uint32
        try:
            self.overlay = Overlay(str(ROOT / "linux/overlay/eye_wifi.bit"), download=True)
            required = {"axi_vdma_0": 0x43000000, "axi_vdma_1": 0x43010000,
                        "live_osd_0": 0x43c00000, "v_tc_0": 0x43c10000}
            for name, address in required.items():
                if self.overlay.ip_dict.get(name, {}).get("phys_addr") != address:
                    raise RuntimeError("Overlay/HWH register map mismatch: " + name)
            for _ in range(5):
                b = allocate(shape=(720, 1280, 3), dtype=np.uint8)
                self.buffers.append(b)
                b.fill(0)
                b.flush()
            if not self.lib.linux_hw_open():
                raise RuntimeError("MMIO/OSD/camera initialization failed; inspect board log")
            self.opened = True
            live = (C.c_uint32 * 3)(*[b.physical_address for b in self.buffers[:3]])
            cap = (C.c_uint32 * 2)(*[b.physical_address for b in self.buffers[3:]])
            if not self.lib.linux_video_init(live, cap):
                raise RuntimeError("VDMA startup failed; no usable frame")
        except BaseException:
            self.close()
            raise
    def snapshot(self):
        import numpy as np
        index = self.lib.linux_snapshot_index()
        if index not in (0, 1):
            raise RuntimeError("VDMA capture timeout/fault")
        source = self.buffers[3 + index]
        source.invalidate()
        # np.array strips PynqBuffer ownership; ndarray.copy may inherit the CMA
        # allocator handle through __array_finalize__ and free a live DMA slot.
        return np.array(source, copy=True, subok=False)
    def publish(self, sequence, sampled):
        if not self.lib.linux_osd_publish(sequence, sampled):
            raise RuntimeError("OSD mailbox timeout")
        if not self.lib.linux_display_health():
            raise RuntimeError("HDMI/live VDMA stalled")
    def clear(self):
        if not self.lib.linux_osd_clear():
            raise RuntimeError("OSD clear timeout")
    def counters(self):
        return dict(cam_frames=self.lib.live_osd_camera_frames(), hdmi_frames=self.lib.live_osd_display_frames(),
                    rx=self.lib.video_rx_status(), tx=self.lib.video_tx_status())
    def close(self):
        if self.opened:
            if not self.lib.linux_hw_close():
                # Download resets the PL including a wedged/partial DMA startup.
                # Retain the allocations if PL reset itself fails.
                self.overlay.download()
            self.opened = False
        for b in self.buffers:
            b.freebuffer()
        self.buffers.clear()
