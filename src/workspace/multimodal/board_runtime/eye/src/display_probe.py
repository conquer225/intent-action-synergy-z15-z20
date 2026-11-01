"""Finite HDMI test; retain CMA until DMA halt, restore original PL afterwards."""
import argparse
import ctypes as C
import fcntl
from pathlib import Path
import signal
import time
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seconds", type=int, default=120)
    args = p.parse_args()
    from pynq import Overlay, PL, allocate
    import numpy as np
    import cv2
    root = Path(__file__).resolve().parents[1]
    lock = open("/run/lock/tobii_display.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    original = PL.bitfile_name
    if not original or not Path(original).exists():
        raise RuntimeError("No original bitfile for restoration")
    print("original_overlay=" + original, flush=True)
    buffers, overlay, mapped = [], None, False
    lib = C.CDLL(str(root / "libtobii_display.so"))
    lib.display_open.argtypes = [C.POINTER(C.c_uint32)]
    lib.display_status.restype = lib.display_frames.restype = C.c_uint32
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        overlay = Overlay(str(root / "overlay/eye_wifi.bit"))
        required = {"axi_vdma_0": 0x43000000, "axi_vdma_1": 0x43010000,
                    "live_osd_0": 0x43c00000, "v_tc_0": 0x43c10000}
        for name, address in required.items():
            if overlay.ip_dict.get(name, {}).get("phys_addr") != address:
                raise RuntimeError("HWH mismatch: " + name)
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[:, :426] = (80, 25, 25)
        frame[:, 426:853] = (25, 80, 25)
        frame[:, 853:] = (25, 25, 80)
        cv2.putText(frame, "Z15 TOBII - HDMI TEST", (245, 90), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (255,255,255), 2)
        cv2.putText(frame, "GAZE NOT VALIDATED", (385, 625), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255,255,255), 2)
        cv2.circle(frame, (640, 360), 18, (255,255,255), -1)
        for _ in range(3):
            b = allocate(shape=frame.shape, dtype=np.uint8)
            buffers.append(b)
            b[:] = frame
            b.flush()
        physical = (C.c_uint32 * 3)(*[b.physical_address for b in buffers])
        mapped = True
        if not lib.display_open(physical):
            raise RuntimeError("Display MMIO/VDMA/VTC initialization failed")
        previous, last_progress = lib.display_frames(), time.monotonic()
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            time.sleep(1)
            count, status = lib.display_frames(), lib.display_status()
            print("hdmi_frames=%d tx_status=%08x" % (count,status), flush=True)
            if status & (0x80000ff0 | 1):
                raise RuntimeError("VDMA fault/halt")
            if count != previous:
                previous, last_progress = count, time.monotonic()
            elif time.monotonic() - last_progress > 2:
                raise RuntimeError("HDMI frame counter stalled")
    except KeyboardInterrupt:
        print("display_interrupted", flush=True)
    finally:
        halted = lib.display_close() if mapped else True
        if not halted:
            overlay.download()
        for b in buffers:
            b.freebuffer()
        if overlay is not None:
            Overlay(original)
            print("restored_overlay=" + original, flush=True)
        lock.close()
if __name__ == "__main__":
    main()
