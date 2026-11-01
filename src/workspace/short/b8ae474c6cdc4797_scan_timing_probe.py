"""Bounded HDMI diagnostics; visible preview requires separate explicit consent."""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

REQUIRED = {"axi_vdma_0": 0x43000000, "axi_vdma_1": 0x43010000,
            "live_osd_0": 0x43c00000, "v_tc_0": 0x43c10000}


def checked_files(state):
    for path, expected in state["hardware_hashes"].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise RuntimeError("Hardware/recovery hash changed: " + path)


def counter_delta(current, previous):
    return (current - previous) & 0xffffffff


def measure(lib, seconds, clock=time.monotonic, sleep=time.sleep, require=None):
    start = clock()
    previous = initial = int(lib.display_frames())
    previous_poll = last_change = start
    polls, changes, intervals = [], [], []
    skipped = 0
    while clock() - start < seconds:
        sleep(.001)
        if require:require()
        count = int(lib.display_frames())
        now = clock()
        polls.append((now - previous_poll) * 1000)
        previous_poll = now
        delta = counter_delta(count, previous)
        if delta:
            if delta > 1000:
                raise RuntimeError("Display counter reset or implausible jump")
            changes.append((now - start, delta))
            if delta == 1 and previous != initial:
                intervals.append((now - last_change) * 1000)
            skipped += max(0, delta - 1)
            previous, last_change = count, now
        elif now - last_change > .2:
            raise RuntimeError("Static HDMI scan counter stalled")
        if lib.display_status() & 0x80000ff1:
            raise RuntimeError("VDMA fault/halt")
    elapsed = clock() - start
    return {"elapsed_s": elapsed, "counter_delta": counter_delta(previous, initial),
            "scan_hz": counter_delta(previous, initial) / elapsed,
            "change_events": changes, "single_increment_intervals_ms": intervals,
            "max_poll_gap_ms": max(polls), "unobserved_individual_increments": skipped,
            "display_status": hex(lib.display_status())}


def fixed_brightness(frames):
    """Exercise the same phase-dependent copies with identical visible patches."""
    for key in list(frames.patches):
        frames.patches[key] = frames.patches[(key[0], False, False)]
    return frames


def visible_preview(state):
    if state.get('probe_mode') != 'visible_display_only':
        return False
    if state.get('visible_flicker_consent') is not True or state['seconds'] != 10:
        raise ValueError('Visible display-only preview requires consent and exactly ten seconds')
    return True


def measure_dynamic(lib, frames, buffers, seconds, clock=time.monotonic, sleep=time.sleep,
                    trace=None):
    from hdmi_stimulus import ScanPump
    from ssvep_hdmi import ScanEvidence
    copies, parks, latches, transfers, stages = [], [], [], [], []
    def timed(stage, index, call):
        started = clock()
        counter = int(lib.display_frames()) if trace else None
        if trace:trace.begin()
        try:return call()
        finally:
            detail = trace.end() if trace else None
            ended = clock()
            (copies if stage == 'prepare' else parks).append((ended-started)*1000)
            if trace:
                stages.append(dict(stage=stage,index=index,started=started,ended=ended,
                                   counter_before=counter,counter_after=int(lib.display_frames()),
                                   sleep=detail))
    def paint(index, mask):
        transfer = timed('prepare',index,lambda:frames.paint(buffers[index],index,mask,clock=clock))
        if isinstance(transfer, dict):transfers.append(transfer)
    class TimedLibrary:
        def __getattr__(self, name):return getattr(lib, name)
        def display_park(self, index):
            return timed('park',index,lambda:lib.display_park(index))
    pump = ScanPump(TimedLibrary(), paint, clock=clock, sleep=sleep)
    start = clock()
    error = origin = evidence = rejected = None
    try:
        origin = pump.begin()
        evidence = ScanEvidence(origin['origin_counter'], origin['presented_monotonic'],
                                origin['active_index'])
        start = clock()
        while clock()-start < seconds:
            row = pump.step()
            try:evidence.observe([row], clock())
            except ValueError:
                rejected = row
                raise
            latches.append(row)
    except ValueError as exc:
        error = str(exc)
    elapsed = clock()-start
    return dict(scope='fixed_brightness_cma_flush_and_scan_latch_only',
                visible_stimulus_tested=False, optical_measurement=False,
                completed=error is None and elapsed>=seconds, error=error,
                elapsed_s=elapsed, origin=origin, latches=latches,
                rejected_latch=rejected, diagnostic_stages=stages,
                verified_single_scan_latches=len(latches),
                copy_and_flush_ms=copies, park_ack_ms=parks,
                preparation='two_future_frames_before_submission',
                transfer_bytes=transfers,
                scan_evidence=evidence.snapshot(clock()) if evidence else None,
                counter=int(lib.display_frames()), active_index=int(lib.display_index()),
                display_status=hex(lib.display_status()))


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True,
                          timeout=20).stdout.strip()


def write_report(state, report):
    target = Path(state["report_path"])
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2))
    temporary.replace(target)


def recover(state, state_path):
    """Timer is limited to this exact unit, script, state and expected overlays."""
    import fcntl
    from pynq import Overlay, PL
    report_path = Path(state["report_path"])
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    if report.get("original_restored") and report.get("buffers_released"):
        return
    unit = state["hardware_unit"]
    owner = int(run("systemctl", "show", unit, "-p", "MainPID", "--value"))
    hardware_lock = None
    if owner:
        argv = (Path("/proc") / str(owner) / "cmdline").read_bytes().split(b"\0")
        if str(Path(__file__).resolve()).encode() not in argv or str(state_path).encode() not in argv:
            raise RuntimeError("Recovery refuses unrelated display process")
        os.kill(owner, signal.SIGTERM)
        deadline = time.monotonic() + 8
        while int(run("systemctl", "show", unit, "-p", "MainPID", "--value")) == owner:
            if time.monotonic() >= deadline:
                break
            time.sleep(.2)
    else:
        hardware_lock = open("/run/lock/guardianloop-pl.lock", "a")
        fcntl.flock(hardware_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with open(state_path.parent / "restore.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        remaining = int(run("systemctl", "show", unit, "-p", "MainPID", "--value"))
        if remaining not in (0, owner):
            raise RuntimeError("Recovery owner PID changed")
        if PL.bitfile_name not in (state["original_overlay"], state["display_overlay"]):
            raise RuntimeError("Recovery refuses unexpected PL owner")
        if PL.bitfile_name != state["original_overlay"] or remaining:
            checked_files(state)
            Overlay(state["original_overlay"])
            if PL.bitfile_name != state["original_overlay"]:
                raise RuntimeError("Emergency restoration did not verify")
        if remaining:
            os.kill(remaining, signal.SIGKILL)
        write_report(dict(state, report_path=str(state_path.parent / "watchdog-report.json")),
                     {"original_restored": True, "owner_terminated": bool(remaining)})
    if hardware_lock:
        hardware_lock.close()


def probe(state, state_path):
    import fcntl
    import numpy as np
    import cv2
    from pynq import Overlay, PL, allocate
    sys.path.insert(0, state["eye_root"] + "/src")
    from coexist_guard import CoexistGuard
    original = state["original_overlay"]
    display = state["display_overlay"]
    report = {"audio_output": False, "physical_output_enabled": False,
              "stimulus_enabled": False, "eye_usb_opened": False,
              "brain_services_stopped": False, "optical_measurement": False,
              "original_restored": False, "buffers_released": False, "errors": []}
    visible = visible_preview(state)
    integrated=state.get('probe_mode')=='integrated_nonflashing'
    dynamic = visible or state.get('probe_mode', 'static') in ('dynamic_nonflashing','integrated_nonflashing')
    report.update(display_only=visible, eeg_decision_started=False,
                  recognition_tested=False, visible_flicker_requested=visible)
    report['probe_mode'] = state.get('probe_mode','static')
    locks, buffers = [], []
    native_worker = None
    watch = None
    attempted = mapped = False
    lib = C.CDLL(state["display_library"])
    lib.display_open.argtypes = [C.POINTER(C.c_uint32)]
    lib.display_open.restype = lib.display_close.restype = C.c_int
    lib.display_park.argtypes = [C.c_uint]
    lib.display_park.restype = C.c_int
    lib.display_index.restype = lib.display_frames.restype = lib.display_status.restype = C.c_uint32
    lib.Xil_In32.argtypes = [C.c_uint32]
    lib.Xil_In32.restype = C.c_uint32

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        for name in ("guardianloop-pl.lock", "tobii_display.lock"):
            handle = open("/run/lock/" + name, "a")
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locks.append(handle)
        if PL.bitfile_name != original:
            raise RuntimeError("Original PL differs from approved recovery target")
        checked_files(state)
        for path,expected in state.get('source_hashes',{}).items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=expected:
                raise RuntimeError('Isolated probe source changed: '+path)
        trace = None
        if state.get('native_scan_library'):
            if not dynamic or state.get('sleep_trace_library'):
                raise RuntimeError('Native scan requires an isolated display probe without sleep tracing')
            from native_scan import NativeOwnershipError, measure_native, preflight
            report['native_scan'] = True
        if state.get('sleep_trace_library'):
            from latch_sleep_trace import SleepTrace
            trace = SleepTrace(state['sleep_trace_library'])
            report['sleep_trace_observation_only'] = True
            report['scheduler'] = dict(policy=os.sched_getscheduler(0),
                affinity=sorted(os.sched_getaffinity(0)),priority=os.getpriority(os.PRIO_PROCESS,0),
                timer_slack_ns=int(Path('/proc/self/timerslack_ns').read_text()))
        guard = CoexistGuard(state["eye_root"], original)
        report["admission"] = guard.verify()
        if dynamic:
            from hdmi_stimulus import StimulusFrames
            from system_hdmi import UnifiedDisplay
            from PIL import Image, ImageDraw
            from system_hdmi import centered_text
            view = UnifiedDisplay(state['eye_root'],live=True)
            frames = StimulusFrames(view)
            if not visible:
                frames = fixed_brightness(frames)
            canvas = Image.fromarray(frames.base[:,:,::-1])
            draw = ImageDraw.Draw(canvas)
            draw.rectangle((0,638,1279,719),fill=(10,19,30))
            centered_text(canvas,view.renderer,
                          ('仅显示闪烁10秒 | 不识别 | 轮椅禁用' if visible else
                           '固定亮度换帧检查 | 不闪烁、不识别 | 轮椅禁用'),
                          (20,642,1260,694),24)
            frames.base = np.asarray(canvas)[:,:,::-1].copy()
            frame = frames.base
        else:
            frame = np.empty((720, 1280, 3), dtype=np.uint8)
            frame[:] = (30, 19, 10)
            cv2.putText(frame, "STATIC HDMI SCAN CHECK - NO FLICKER", (170, 300),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (210, 230, 230), 2)
            cv2.putText(frame, "NO AUDIO / NO WHEELCHAIR OUTPUT", (230, 395),
                        cv2.FONT_HERSHEY_SIMPLEX, .9, (170, 190, 200), 2)
        for _ in range(3):
            buffer = allocate(shape=frame.shape, dtype=np.uint8)
            buffers.append(buffer)
            if dynamic:frames.paint(buffer,len(buffers)-1,15)
            else:
                buffer[:] = frame
                buffer.flush()
        if dynamic:
            fixed_sha=hashlib.sha256(buffers[0].tobytes()).hexdigest()
            if any(hashlib.sha256(b.tobytes()).hexdigest()!=fixed_sha for b in buffers):
                raise RuntimeError('Fixed-brightness buffers differ before display')
            report['fixed_frame_sha256']=fixed_sha
        if state.get('native_scan_library'):
            report['native_preflight']=preflight(lib,frames,buffers,state['seconds'],
                                                 state['native_scan_library'])
        attempted = True
        overlay = Overlay(display)
        if any(overlay.ip_dict.get(name, {}).get("phys_addr") != address
               for name, address in REQUIRED.items()):
            raise RuntimeError("Display HWH address mismatch")
        mapped = True
        addresses = (C.c_uint32 * 3)(*[b.physical_address for b in buffers])
        if not lib.display_open(addresses) or not lib.display_park(0):
            raise RuntimeError("Static display initialization failed")
        # PG016: generated active dimensions and horizontal/vertical totals.
        offsets = (0x00, 0x04, 0x60, 0x64, 0x68, 0x6c, 0x70, 0x74, 0x78, 0x7c, 0x80)
        registers = {hex(offset): int(lib.Xil_In32(REQUIRED["v_tc_0"] + offset))
                     for offset in offsets}
        active = registers["0x60"]
        report["vtc"] = {"registers": registers,
                         "active_width": active & 0x1fff,
                         "active_height": (active >> 16) & 0x1fff,
                         "horizontal_total": registers["0x70"] & 0x1fff,
                         "vertical_total_f0": registers["0x74"] & 0x1fff}
        if dynamic and (report['vtc']['active_width'],report['vtc']['active_height'],
                        report['vtc']['horizontal_total'],report['vtc']['vertical_total_f0']) != (1280,720,1650,750):
            raise RuntimeError('Dynamic probe mode differs from the verified scan configuration')
        time.sleep(.5)
        if state.get('runtime_guard_diagnostics'):
            from system_hdmi import RuntimeWatch
            from playback_policy import RecentSamples
            def checked_runtime():
                if PL.bitfile_name!=display:raise RuntimeError('Display PL ownership changed')
                guard.check_runtime()
            checked_runtime()
            watch=RuntimeWatch(checked_runtime)
            watch.check_ms=RecentSamples()
            report['runtime_scheduler']=dict(policy=os.sched_getscheduler(0),
                nice=os.getpriority(os.PRIO_PROCESS,0),affinity=sorted(os.sched_getaffinity(0)))
        print('VISIBLE_DISPLAY_ONLY_STARTED' if visible else
              "DYNAMIC_NO_FLICKER_LATCH_STARTED" if dynamic else "STATIC_HDMI_SCAN_STARTED", flush=True)
        if state.get('native_scan_library'):
            try:
                if integrated:
                    from hdmi_integration_probe import measure_integrated
                    report['measurement']=measure_integrated(lib,frames,buffers,view,
                                                            state['native_scan_library'],state['seconds'])
                else:
                    report['measurement']=measure_native(lib,frames,buffers,state['seconds'],
                                                         state['native_scan_library'])
            except NativeOwnershipError as error:
                native_worker=error.worker
                raise
        else:
            report["measurement"] = (measure_dynamic(lib,frames,buffers,state['seconds'],trace=trace) if dynamic
                                     else measure(lib,state['seconds'],require=watch.require if watch else None))
        if dynamic:
            measurement=report['measurement']
            if visible:
                measurement.update(scope='visible_four_corner_display_only',
                    visible_stimulus_tested=measurement['verified_single_scan_latches'] > 0,
                    recognition_tested=False)
            report['pixels_constant']=all(hashlib.sha256(b.tobytes()).hexdigest()==fixed_sha for b in buffers)
            for key in ('copy_and_flush_ms','park_ack_ms'):
                values=measurement.get(key,[])
                if values:measurement[key+'_summary']=dict(median=float(np.median(values)),
                    p95=float(np.percentile(values,95)),maximum=max(values))
            for key in ('copy_ms','flush_ms','flushed_bytes'):
                values=[row[key] for row in measurement.get('transfer_bytes',[]) if key in row]
                if values:measurement[key+'_summary']=dict(median=float(np.median(values)),
                    p95=float(np.percentile(values,95)),maximum=max(values))
            if measurement['error']:report['errors'].append('Dynamic latch rejected: '+measurement['error'])
            if not visible and not report['pixels_constant']:
                report['errors'].append('Fixed-brightness pixels changed')
        intervals = report["measurement"].get("single_increment_intervals_ms", [])
        if intervals:
            report["measurement"]["interval_summary_ms"] = {
                "median": float(np.median(intervals)),
                "p95": float(np.percentile(intervals, 95)), "maximum": max(intervals)}
        guard.check_runtime()
        if PL.bitfile_name != display:
            raise RuntimeError("Display ownership changed during probe")
    except KeyboardInterrupt:
        report["controlled_stop"] = True
    except Exception as error:
        report["errors"].append(str(error))
    finally:
        if watch:
            report['runtime_watch']=watch.snapshot()
            report['runtime_check_ms']=watch.check_ms
            try:watch.close()
            except RuntimeError as error:report['errors'].append('Runtime watch cleanup: '+str(error))
        with open(state_path.parent / "restore.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                if native_worker is not None:
                    raise RuntimeError('Native thread ownership unresolved; retain CMA for independent recovery')
                halted = bool(lib.display_close()) if mapped else True
                report["display_halted"] = halted
                def restore():
                    checked_files(state)
                    Overlay(original)
                    if PL.bitfile_name != original:
                        raise RuntimeError("Original PL recovery did not verify")
                    report["original_restored"] = True
                if not halted:
                    restore()
                for buffer in buffers:
                    buffer.freebuffer()
                report["buffers_released"] = True
                if attempted and not report["original_restored"]:
                    restore()
                if not attempted:
                    report["original_restored"] = PL.bitfile_name == original
            except Exception as error:
                report["errors"].append("Recovery: " + str(error))
        write_report(state, report)
        print(json.dumps({k: v for k, v in report.items() if k != "measurement"}), flush=True)
        if not report["buffers_released"]:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            while True:
                time.sleep(1)
        for lock in locks:
            lock.close()
    if report["errors"]:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--recover", action="store_true")
    args = parser.parse_args()
    path = args.state.resolve()
    if path.parent != Path(__file__).resolve().parent:
        raise ValueError("State must belong to this isolated stage")
    state = json.loads(path.read_text())
    if not 5 <= state["seconds"] <= 45 or Path(state["report_path"]).parent != path.parent:
        raise ValueError("Probe duration/report outside approved bounds")
    if state.get('probe_mode','static') not in ('static','dynamic_nonflashing','integrated_nonflashing','visible_display_only'):
        raise ValueError('Unapproved display probe mode')
    visible_preview(state)
    for folder in reversed(state.get('software_paths',[])):sys.path.insert(0,folder)
    (recover if args.recover else probe)(state, path)


if __name__ == "__main__":
    main()
