"""Finite video-to-HDMI comparison, with retained buffers and explicit PL recovery."""
import ctypes as C
import fcntl
import hashlib
import json
from pathlib import Path
import resource
import signal
import subprocess
import time

import numpy as np
from pynq import PL, Overlay, allocate

from bench_decoder import load_decoder

BASE = Path(__file__).resolve().parent
STATE = json.loads((BASE / "playback_state.json").read_text())
ORIGINAL = STATE["original_overlay"]
DISPLAY = STATE["display_overlay"]
SERVICE = "guardianloop-cyton.service"
REQUIRED = {"axi_vdma_0": 0x43000000, "axi_vdma_1": 0x43010000,
            "live_osd_0": 0x43c00000, "v_tc_0": 0x43c10000}


def run(*args):
    return subprocess.run(args, capture_output=True, text=True,
                          check=True, timeout=20).stdout.strip()


def service_state():
    return run("systemctl", "show", SERVICE, "-p", "ActiveState", "--value")


def check_files():
    for path, expected in STATE["hardware_hashes"].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise RuntimeError("Playback/recovery artifact checksum changed")


def stopped(*_):
    raise KeyboardInterrupt


def phase(lib, decoder, buffers, cached, path, mode, duration=12):
    reader = decoder.video_open(str(path).encode(), 2) if mode != "cache" else None
    if mode != "cache" and not reader:
        raise RuntimeError("Cannot reopen converted video")
    temporary = np.empty((720, 1280, 3), dtype=np.uint8) if mode == "copy" else None
    stage_ms = {key: [] for key in ("decode", "copy", "flush", "park", "scan")}
    timestamps, late = [], 0
    source_index = 0
    start = time.monotonic()
    first_counter = lib.display_frames()
    cpu = time.process_time()
    try:
        while time.monotonic() - start < duration:
            deadline = start + len(timestamps) / 20
            delay = deadline - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            elif delay < -.05:
                late += 1
            active = lib.display_index()
            if active > 2:
                raise RuntimeError("Unexpected display buffer index")
            index = (active + 1) % 3
            target = buffers[index]
            before = time.monotonic()
            if mode == "cache":
                np.copyto(target, cached[source_index % len(cached)])
                stage_ms["copy"].append((time.monotonic() - before) * 1000)
                source_index += 1
            else:
                destination = target if mode == "direct" else temporary
                result = decoder.video_read_to(reader, destination.ctypes.data,
                                               1280, 720, 3840)
                if result == 0:
                    if decoder.video_rewind(reader) < 0:
                        raise RuntimeError("Video rewind failed")
                    result = decoder.video_read_to(reader, destination.ctypes.data,
                                                  1280, 720, 3840)
                if result != 1:
                    raise RuntimeError("Video decode failed: %d" % result)
                stage_ms["decode"].append((time.monotonic() - before) * 1000)
                if mode == "copy":
                    before = time.monotonic()
                    np.copyto(target, temporary)
                    stage_ms["copy"].append((time.monotonic() - before) * 1000)
            before = time.monotonic()
            target.flush()
            stage_ms["flush"].append((time.monotonic() - before) * 1000)
            before = time.monotonic()
            if not lib.display_park(index) or lib.display_index() != index:
                raise RuntimeError("Frame did not latch into the display channel")
            stage_ms["park"].append((time.monotonic() - before) * 1000)
            # Refresh progress alone is not a video FPS counter: first latch a
            # new source frame, then require a scan progression before reusing it.
            before = time.monotonic()
            count = lib.display_frames()
            while lib.display_frames() == count:
                if time.monotonic() - before > .1:
                    raise RuntimeError("HDMI scan counter stalled")
                time.sleep(.001)
            stage_ms["scan"].append((time.monotonic() - before) * 1000)
            if lib.display_status() & 0x80000ff1:
                raise RuntimeError("Display VDMA error/halt")
            timestamps.append(time.monotonic() - start)
    finally:
        if reader:
            decoder.video_close(reader)
    elapsed = time.monotonic() - start
    full_seconds = int(min(duration, elapsed))
    buckets = [sum(second <= value < second + 1 for value in timestamps)
               for second in range(full_seconds)]
    result = {"mode": mode, "elapsed_s": elapsed, "presented_new_frames": len(timestamps),
        "latched_video_fps": len(timestamps) / elapsed,
        "minimum_full_second_frames": min(buckets), "one_second_frames": buckets,
        "target_fps": 20, "late_frames": late,
        "scan_counter_delta": (lib.display_frames() - first_counter) & 0xffffffff,
        "display_status": hex(lib.display_status()),
        "process_cpu_percent": (time.process_time() - cpu) / elapsed * 100,
        "stage_ms": {key: {"mean": float(np.mean(values)), "p95": float(np.percentile(values, 95))}
                     for key, values in stage_ms.items() if values}}
    result["meets_16fps"] = result["latched_video_fps"] >= 16 and min(buckets) >= 16
    print(json.dumps({"phase_result": result}), flush=True)
    return result


def main():
    report = {"physical_screen_seen": "awaiting user confirmation", "audio_tested": False,
              "phases": [], "original_overlay": ORIGINAL, "display_overlay": DISPLAY,
              "original_restored": False, "buffers_released": False, "service_restored": False}
    locks, buffers = [], []
    mapped = attempted = was_active = False
    overlay = None
    lib = C.CDLL(str(BASE / "libtobii_display.so"))
    lib.display_open.argtypes = [C.POINTER(C.c_uint32)]
    lib.display_open.restype = C.c_int
    lib.display_park.argtypes = [C.c_uint]
    lib.display_park.restype = C.c_int
    lib.display_status.restype = lib.display_frames.restype = lib.display_index.restype = C.c_uint32
    lib.display_close.restype = C.c_int
    signal.signal(signal.SIGINT, stopped)
    signal.signal(signal.SIGTERM, stopped)
    try:
        for name in ("guardianloop-pl.lock", "tobii_display.lock"):
            handle = open("/run/lock/" + name, "a")
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locks.append(handle)
        if PL.bitfile_name != ORIGINAL:
            raise RuntimeError("Current overlay differs from the audited original")
        check_files()
        modules = Path("/proc/modules").read_text()
        if any(line.split()[0].startswith("gldma") for line in modules.splitlines()) or \
           Path("/dev/guardianloop_dma_keeper").exists():
            raise RuntimeError("DMA keeper is present; PL switching is forbidden")
        startup = json.loads(Path("/run/guardianloop-startup/status.json").read_text())
        if startup.get("boot_id") != Path("/proc/sys/kernel/random/boot_id").read_text().strip() or \
           startup.get("pl", {}).get("used_by_current_cap") is not False:
            raise RuntimeError("Current ARM-only brain runtime is not verified")
        was_active = service_state() == "active"
        if not was_active:
            raise RuntimeError("Formal service is not in its expected initial state")
        run("systemctl", "stop", SERVICE)
        if service_state() not in ("inactive", "failed"):
            raise RuntimeError("Acquisition did not stop")
        decoder = load_decoder(BASE / "frame_decoder.so")
        converted = json.loads((BASE / "conversion_report.json").read_text())["conversions"][0]
        frames = converted["encoded_frames"]
        if not 1 <= frames <= 64:
            raise RuntimeError("This finite clip exceeds the bounded RAM-cache trial")
        path = Path(converted["path"])
        cached = np.empty((frames, 720, 1280, 3), dtype=np.uint8)
        reader = decoder.video_open(str(path).encode(), 2)
        if not reader:
            raise RuntimeError("Cannot predecode finite clip")
        try:
            for frame in cached:
                if decoder.video_read_to(reader, frame.ctypes.data, 1280, 720, 3840) != 1:
                    raise RuntimeError("Frame-cache source count differs")
            scratch = np.empty((720, 1280, 3), dtype=np.uint8)
            if decoder.video_read_to(reader, scratch.ctypes.data, 1280, 720, 3840) != 0:
                raise RuntimeError("Frame-cache source has extra frames")
            for _ in range(3):
                buffer = allocate(shape=(720, 1280, 3), dtype=np.uint8)
                buffers.append(buffer)
                np.copyto(buffer, cached[0])
                buffer.flush()
            if decoder.video_rewind(reader) < 0 or \
               decoder.video_read_to(reader, buffers[0].ctypes.data, 1280, 720, 3840) != 1 or \
               not np.array_equal(buffers[0], cached[0]):
                raise RuntimeError("Direct CMA output differs from cached output")
            buffers[0].flush()
            report["direct_output_matches_cached_first_frame"] = True
            report["predecoded_cache_mib"] = cached.nbytes / 1024 ** 2
        finally:
            decoder.video_close(reader)
        attempted = True
        overlay = Overlay(DISPLAY)
        if any(overlay.ip_dict.get(name, {}).get("phys_addr") != address
               for name, address in REQUIRED.items()):
            raise RuntimeError("Display HWH address mismatch")
        physical = (C.c_uint32 * 3)(*[buffer.physical_address for buffer in buffers])
        mapped = True
        if not lib.display_open(physical) or not lib.display_park(0):
            raise RuntimeError("Display initialization failed")
        print("HDMI_VIDEO_VISIBLE_TEST_STARTED", flush=True)
        for mode in ("copy", "direct", "cache"):
            report["phases"].append(phase(lib, decoder, buffers, cached, path, mode))
            (BASE / "display_report.json").write_text(json.dumps(report, indent=2))
        acceptable = [item for item in report["phases"] if item["meets_16fps"]]
        if acceptable:
            chosen = max(acceptable, key=lambda item: (item["minimum_full_second_frames"], item["latched_video_fps"]))
            report["selected_mode"] = chosen["mode"]
            report["confirmation"] = phase(lib, decoder, buffers, cached, path, chosen["mode"], 20)
        report["meets_16fps"] = bool(acceptable) and report["confirmation"]["meets_16fps"]
    except KeyboardInterrupt:
        report["interrupted"] = True
    except Exception as error:
        report["error"] = str(error)
    finally:
        recovery_lock = open(str(BASE / "restore.lock"), "a")
        try:
            fcntl.flock(recovery_lock, fcntl.LOCK_EX)
            halted = bool(lib.display_close()) if mapped else True
            report["display_halted"] = halted
            if not halted:
                check_files()
                Overlay(ORIGINAL)
                report["original_restored"] = PL.bitfile_name == ORIGINAL
                if not report["original_restored"]:
                    raise RuntimeError("Display DMA reset did not verify; retain its buffers")
            for buffer in buffers:
                buffer.freebuffer()
            report["buffers_released"] = True
            if attempted and not report["original_restored"]:
                check_files()
                Overlay(ORIGINAL)
                report["original_restored"] = PL.bitfile_name == ORIGINAL
            elif not attempted:
                report["original_restored"] = PL.bitfile_name == ORIGINAL
            if not report["original_restored"]:
                raise RuntimeError("Original PL restoration did not verify")
            if was_active:
                run("systemctl", "start", SERVICE)
                report["service_restored"] = service_state() == "active"
        except Exception as error:
            report["recovery_error"] = str(error)
        finally:
            recovery_lock.close()
            report["peak_rss_mib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
            (BASE / "display_report.json").write_text(json.dumps(report, indent=2))
            print(json.dumps({"display_final": report}), flush=True)
        if not report["buffers_released"]:
            print("CMA_OWNERSHIP_RETAINED_WAITING_FOR_RECOVERY", flush=True)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            while True:
                time.sleep(1)
        for lock in locks:
            lock.close()
    if report.get("error") or report.get("recovery_error"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
