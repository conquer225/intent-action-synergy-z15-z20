"""Finite real-asset check; no human calibration or simulated gaze acceptance."""
import argparse
import ctypes as C
import fcntl
import json
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from media_menu import MenuView
from media_players import Asset, AudioPlayer, VideoPlayer
from guide_render import Renderer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, default=ROOT / "media_smoke")
    parser.add_argument("--hdmi", action="store_true")
    args = parser.parse_args()
    video = VideoPlayer()
    renderer = Renderer(local_media=True)
    overlay = lib = lock = None
    buffers, mapped = [], False
    report = {"gaze_acceptance": "not tested", "audibility": "not tested"}
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        if args.hdmi:
            from pynq import PL, Overlay, allocate
            import numpy as np
            lock = open("/run/lock/tobii_display.lock", "w")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            original = PL.bitfile_name
            if not original or not Path(original).is_file():
                raise RuntimeError("Original overlay unavailable")
            overlay = Overlay(str(ROOT / "overlay/eye_wifi.bit"))
            for name, address in {"axi_vdma_0":0x43000000,"axi_vdma_1":0x43010000,
                                  "live_osd_0":0x43c00000,"v_tc_0":0x43c10000}.items():
                if overlay.ip_dict.get(name, {}).get("phys_addr") != address:
                    raise RuntimeError("HWH mismatch: " + name)
            lib = C.CDLL(str(ROOT / "libtobii_display.so"))
            lib.display_open.argtypes = [C.POINTER(C.c_uint32)]
            lib.display_park.argtypes = [C.c_uint]
            lib.display_status.restype = lib.display_frames.restype = C.c_uint32
            for _ in range(3):
                buffer = allocate(shape=(720,1280,3), dtype=np.uint8)
                buffers.append(buffer)
                buffer[:] = 0
                buffer.flush()
            physical = (C.c_uint32 * 3)(*[b.physical_address for b in buffers])
            mapped = True
            if not lib.display_open(physical):
                raise RuntimeError("HDMI initialization failed")
            initial_counter = lib.display_frames()
        asset = Asset("小狗", args.samples / "videos/02", 102, 10)
        if not video.start(asset):
            raise RuntimeError(video.error)
        started = time.monotonic()
        indices, costs = [], []
        current = 0
        while time.monotonic() - started < 15:
            loop = time.monotonic()
            frame, status, error = video.poll()
            if error:
                raise RuntimeError(error)
            if frame is not None:
                index, picture = frame
                pixels = renderer.render(MenuView(phase="video", title="正在观看",
                    footer="无声视频 · 播放中暂停眼控 · PS_KEY1 退出",
                    video_frame=index, video_image=picture))
                if lib:
                    current = (current+1) % 3
                    buffers[current][:] = pixels
                    buffers[current].flush()
                    if not lib.display_park(current):
                        raise RuntimeError("HDMI park failed")
                    if lib.display_status() & 0xff1:
                        raise RuntimeError("HDMI VDMA fault/halt")
                indices.append(index)
                costs.append(time.monotonic() - loop)
            if status == "complete":
                break
            time.sleep(max(.001,.1-(time.monotonic()-loop)))
        if video.status != "complete":
            raise RuntimeError("Video did not complete within 15 seconds")
        report.update(expected_seconds=10.2, elapsed_seconds=round(time.monotonic()-started,3),
            presented_frames=len(indices), first_frame=indices[0], last_frame=indices[-1],
            skipped_frames=sum(max(0,b-a-1) for a,b in zip(indices,indices[1:])),
            max_queue_size=video.latest.maxsize,
            render_copy_flush_park_ms_mean=round(sum(costs)/len(costs)*1000,2),
            render_copy_flush_park_ms_max=round(max(costs)*1000,2))
        if lib:
            report.update(hdmi_counter_delta=lib.display_frames()-initial_counter,
                          hdmi_status=hex(lib.display_status()))
        audio = AudioPlayer()
        try:
            if audio.start(args.samples / "speech/01.wav"):
                until = time.monotonic() + 5
                result = None
                while time.monotonic() < until and result is None:
                    result = audio.poll()
                    time.sleep(.02)
                report["default_audio_result"] = result or ("timeout","")
            else:
                report["default_audio_result"] = (audio.status,audio.error)
        finally:
            audio.close()
    finally:
        video.close()
        if lib:
            halted = lib.display_close() if mapped else True
            if not halted:
                overlay.download()
        for buffer in buffers:
            buffer.freebuffer()
        if overlay:
            Overlay(original)
            report["restored_overlay"] = original
        if lock:
            lock.close()
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__ == "__main__":
    main()
