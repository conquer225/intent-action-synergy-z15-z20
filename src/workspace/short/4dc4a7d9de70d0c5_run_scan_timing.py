"""Explicit stage/launch/collect for the user-authorized static HDMI check."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import uuid

import run_live_system as board

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output/scan_timing_20261008"
LAUNCH = OUT / "launch.json"
PYTHON = board.PYTHON
SLEEP_TRACE = False
NATIVE_SCAN = False
INTEGRATED=False
SOFTWARE_RUN='hdmi_candidate_20261008'


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def stage(client, media):
    if LAUNCH.exists():
        raise ValueError("Existing scan stage must be inspected, not overwritten")
    before = board.audit(client, media)
    if not before["release_unchanged"] or before["pl"] != media["original_overlay"]:
        raise ValueError("Formal admission changed")
    eye = media["eye_root"]
    code = ("from coexist_guard import CoexistGuard; from pynq import PL; "
            "import json; print(json.dumps(CoexistGuard(" + repr(eye) +
            ",PL.bitfile_name).verify()))")
    admission = json.loads(board.execute(client, shlex.join([
        "env", "XILINX_XRT=/usr", "PYTHONPATH=" + eye + "/src", PYTHON, "-c", code]), True))
    save("before.json", before)
    dynamic = OUT.name.startswith('dynamic_latch_20261008')
    ident = ("gl-latch-20261008-" if dynamic else "gl-scan-20261008-") + uuid.uuid4().hex[:8]
    remote = "/home/xilinx/" + ident
    paths = [media["original_overlay"], media["original_overlay"].replace(".bit", ".hwh"),
             eye + "/overlay/eye_wifi.bit", eye + "/overlay/eye_wifi.hwh",
             eye + "/libtobii_display.so"]
    hashes = {path: board.execute(client, shlex.join(["sha256sum", path]), True).split()[0]
              for path in paths}
    if hashes[paths[0]] != "c39b891704471a712fb7be3591841af1dd6791387957b873b11450c99eca41ca":
        raise ValueError("Recovery bit differs from approved formal artifact")
    if hashes[paths[-1]] != "f0e12abe7901c3b98843a10135f1ce98d0507d3ef518a9836186ceab4d1e9da9":
        raise ValueError("Display library differs from inspected frame-counter binary")
    if dynamic:
        previous=json.loads((ROOT/'output/scan_timing_20261008/launch.json').read_text(encoding='utf-8'))
        if hashes!=previous['config']['hardware_hashes']:
            raise ValueError('Artifacts differ from the approved static-scan baseline')
    config = {"hardware_unit": ident + ".service", "original_overlay": paths[0],
              "display_overlay": paths[2], "display_library": paths[-1],
              "eye_root": eye, "seconds": 30, "hardware_hashes": hashes,
              "report_path": remote + "/scan-report.json"}
    if dynamic:
        bundle=json.loads((ROOT/'output'/SOFTWARE_RUN/'stage.json').read_text(encoding='utf-8'))
        software=bundle['remote']
        raw=board.execute(client,shlex.join(['sha256sum',*[software+'/'+name for name in bundle['hashes']]]))
        actuals={line.split(maxsplit=1)[1].strip():line.split(maxsplit=1)[0] for line in raw.splitlines()}
        for name,sha in bundle['hashes'].items():
            if actuals.get(software+'/'+name)!=sha:
                raise ValueError('Candidate software bundle changed: '+name)
        save('candidate-manifest.json',bundle)
        config.update(probe_mode='integrated_nonflashing' if INTEGRATED else 'dynamic_nonflashing',software_paths=[software+'/runtime',
                      software+'/phone_video_upload',software,eye+'/src'])
        config['source_hashes']={software+'/'+name:sha for name,sha in bundle['hashes'].items()}
        save('source-mode.json',dict(visible_brightness_fixed=True,eeg_session_started=False))
    board.execute(client, shlex.join(["mkdir", "-m", "700", remote]))
    with client.open_sftp() as ftp:
        sources = ["scan_timing_probe.py", "test_scan_timing_probe.py"]
        if SLEEP_TRACE:sources.extend(['latch_sleep_trace.c','latch_sleep_trace.py'])
        if NATIVE_SCAN:sources.extend(['native_scan.c','native_scan.py','test_native_scan.py'])
        if INTEGRATED:sources.extend(['hdmi_integration_probe.py','test_hdmi_integration_probe.py'])
        for name in sources:
            ftp.put(str(ROOT / name), remote + "/" + name)
            ftp.chmod(remote + "/" + name, 0o600)
            actual = board.execute(client, shlex.join(["sha256sum", remote + "/" + name])).split()[0]
            if actual != hashlib.sha256((ROOT / name).read_bytes()).hexdigest():
                raise ValueError("Probe source transfer changed")
            if dynamic:config['source_hashes'][remote+'/'+name]=actual
    if SLEEP_TRACE:
        library=remote+'/liblatch_sleep_trace.so'
        compile_args=['gcc','-O2','-Wall','-Wextra','-Werror','-fPIC','-shared',
                      remote+'/latch_sleep_trace.c','-o',library,'-ldl']
        board.execute(client,shlex.join(compile_args))
        config['sleep_trace_library']=library
        config['source_hashes'][library]=board.execute(client,shlex.join(['sha256sum',library])).split()[0]
        code='from latch_sleep_trace import selftest; selftest('+repr(library)+')'
        output=board.execute(client,shlex.join(['env','LD_PRELOAD='+library,
                                              'PYTHONPATH='+remote,PYTHON,'-c',code]))
        save('sleep-trace-selftest.json',json.loads(output))
        print('NANOSLEEP_TRACE_SOFTWARE_SELFTEST_PASSED_NO_PL_CHANGE')
    if NATIVE_SCAN:
        library=remote+'/libnative_scan.so'
        compile_args=['gcc','-std=gnu11','-O3','-mcpu=cortex-a9','-mfpu=neon',
                      '-Wall','-Wextra','-Werror','-fPIC','-shared','-pthread',
                      remote+'/native_scan.c','-o',library]
        board.execute(client,shlex.join(compile_args))
        config['native_scan_library']=library
        config['source_hashes'][library]=board.execute(client,shlex.join(['sha256sum',library])).split()[0]
        config['native_worker_limits']=dict(policy='SCHED_RR',priority=1,cpu=1,
                                           cycle_cpu_budget_ms=8,duration_s=30)
    with client.open_sftp() as ftp:
        with ftp.open(remote + "/state.json", "w") as handle:
            handle.write(json.dumps(config))
        ftp.chmod(remote + "/state.json", 0o600)
    test_args=["env", "OPENBLAS_NUM_THREADS=1", "PYTHONPATH=" + ':'.join([remote,*config.get('software_paths',[])]),
               'GL_TEST_EYE_ROOT='+eye]
    if NATIVE_SCAN:test_args.append('GL_NATIVE_SCAN_LIBRARY='+config['native_scan_library'])
    test_args.extend([PYTHON,'-m','unittest',
                     'test_scan_timing_probe' if dynamic else 'test_scan_timing_probe.ScanTests'])
    if NATIVE_SCAN:test_args.append('test_native_scan.NativeTests')
    if INTEGRATED:test_args.append('test_hdmi_integration_probe')
    command=shlex.join(test_args+['-v'])
    _,stdout,stderr=client.exec_command(command,timeout=240)
    output=stdout.read().decode(errors='replace')+stderr.read().decode(errors='replace')
    exit_code=stdout.channel.recv_exit_status()
    save('software-tests.json',dict(remote=remote,output=output,exit_code=exit_code,hardware_tested=False))
    print(output)
    if exit_code:raise RuntimeError('Probe software check failed; full diagnostics retained')
    if NATIVE_SCAN:
        code=('import sys,unittest; suite=unittest.defaultTestLoader.loadTestsFromName('
              "'test_native_scan.BoardPreflightTests'); "
              'result=unittest.TextTestRunner(stream=sys.stdout,verbosity=2).run(suite); '
              'sys.exit(not result.wasSuccessful())')
        command=shlex.join(['env','XILINX_XRT=/usr','OPENBLAS_NUM_THREADS=1',
            'PYTHONPATH='+':'.join([remote,*config['software_paths']]),
            'GL_NATIVE_SCAN_LIBRARY='+config['native_scan_library'],
            'GL_NATIVE_BOARD_PREFLIGHT='+eye+'/libtobii_display.so',PYTHON,'-c',code])
        result=board.execute(client,command,True)
        save('native-board-preflight.json',dict(output=result,pl_loaded=False,
            display_functions_called=False,native_worker_started=False))
        print(result)
    save("launch.json", {"remote": remote, "unit": ident, "config": config,
                         "admission": admission, "launched": False})
    print("DYNAMIC_NONFLASHING_PROBE_STAGED_NO_PL_CHANGE" if dynamic else "STATIC_PROBE_STAGED_NO_PL_CHANGE")


def launch(client, media):
    stage_info = json.loads(LAUNCH.read_text(encoding="utf-8"))
    if stage_info["launched"]:
        raise ValueError("Probe already launched; use status/collect")
    current = board.audit(client, media)
    before = json.loads((OUT / "before.json").read_text(encoding="utf-8"))
    if current != before:
        raise ValueError("Board changed after read-only preflight")
    remote, unit = stage_info["remote"], stage_info["unit"]
    link=board.execute(client,shlex.join(['iw','dev','wlan0','link']))
    if (stage_info['config'].get('sleep_trace_library') or stage_info['config'].get('native_scan_library')) and 'SSID: QqqQ' not in link:
        raise ValueError('User-requested phone hotspot is no longer connected')
    command = ["env", "XILINX_XRT=/usr", "OPENBLAS_NUM_THREADS=1", PYTHON,
               remote + "/scan_timing_probe.py", "--state", remote + "/state.json"]
    # Candidate font rendering happens before PL loading; sampling remains 30 s.
    recovery_delay='150s' if (stage_info['config'].get('probe_mode') in ('dynamic_nonflashing','integrated_nonflashing')
                            or stage_info['config'].get('runtime_guard_diagnostics')) else '75s'
    print(board.execute(client, shlex.join([
        "systemd-run", "--unit=" + unit + "-recover", "--on-active="+recovery_delay,
        "--timer-property=AccuracySec=1s"] + command + ["--recover"]), True))
    probe_command=list(command)
    if stage_info['config'].get('sleep_trace_library'):
        probe_command.insert(1,'LD_PRELOAD='+stage_info['config']['sleep_trace_library'])
    priority=['--property=Nice=5'] if stage_info['config'].get('runtime_guard_diagnostics') else []
    print(board.execute(client, shlex.join([
        "systemd-run", "--unit=" + unit, "--property=TimeoutStopSec=infinity",
        "--property=KillMode=process", "--property=LimitCORE=0"] + priority + probe_command), True))
    stage_info["launched"] = True
    stage_info['recovery_delay']=recovery_delay
    save("launch.json", stage_info)
    print("BOUNDED_PROBE_LAUNCHED_WITH_INDEPENDENT_RECOVERY")


def status(client, media):
    info = json.loads(LAUNCH.read_text(encoding="utf-8"))
    print(board.execute(client, shlex.join(["systemctl", "show", info["unit"],
          "-p", "MainPID", "-p", "ActiveState", "-p", "Result", "-p", "ExecMainStatus"])))
    print(board.execute(client, shlex.join(["journalctl", "-u", info["unit"],
          "--no-pager", "-n", "12"]), True))


def collect(client, media):
    info = json.loads(LAUNCH.read_text(encoding="utf-8"))
    raw = board.execute(client, shlex.join(["cat", info["config"]["report_path"]]), True)
    report = json.loads(raw)
    save("scan-report.json", report)
    before = json.loads((OUT / "before.json").read_text(encoding="utf-8"))
    after = board.audit(client, media)
    after.update(protected_unchanged=after["protected"] == before["protected"],
                 services_unchanged=after["services"] == before["services"],
                 boot_unchanged=after["boot"] == before["boot"],
                 original_pl_restored=after["pl"] == media["original_overlay"])
    save("after.json", after)
    if not report["original_restored"] or not report["buffers_released"] or not after["original_pl_restored"]:
        raise RuntimeError("Recovery not verified; retain independent timer")
    timer = info["unit"] + "-recover.timer"
    loaded = board.execute(client, shlex.join([
        "systemctl", "show", timer, "-p", "LoadState", "--value"])).strip()
    if loaded != "not-found":
        board.execute(client, shlex.join(["systemctl", "stop", timer]), True)
    save("unit-status.json", {"display": board.execute(client, shlex.join([
        "systemctl", "show", info["unit"], "-p", "MainPID", "-p", "ActiveState",
        "-p", "Result", "-p", "ExecMainStatus"])),
        "recovery_timer": board.execute(client, shlex.join([
            "systemctl", "show", timer, "-p", "LoadState", "-p", "ActiveState"])),
        "journal": board.execute(client, shlex.join([
            "journalctl", "-u", info["unit"], "--no-pager", "-n", "20"]), True)})
    summary = {k: v for k, v in report.items() if k not in ("measurement", "admission")}
    summary["scan"] = {k: v for k, v in report.get("measurement", {}).items()
                       if k not in ("change_events", "single_increment_intervals_ms",'latches',
                                    'copy_and_flush_ms','park_ack_ms','transfer_bytes','diagnostic_stages',
                                    'copy_ms','flush_ms','sessions')}
    if 'sessions' in report.get('measurement', {}):
        summary['scan']['session_receipt_counts'] = [len(row['latches'])
            for row in report['measurement']['sessions']]
    summary["after"] = {k: v for k, v in after.items() if k not in ("protected", "services")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("stage", "launch", "status", "collect"))
    parser.add_argument('--mode',choices=('static','dynamic_nonflashing'),default='static')
    parser.add_argument('--run-id', help='Unique evidence suffix; never reuses a launched stage')
    parser.add_argument('--sleep-trace', action='store_true', help='Observation-only diagnostic in this process')
    parser.add_argument('--native-scan', action='store_true', help='Bounded isolated native worker, fixed brightness only')
    parser.add_argument('--integrated',action='store_true',help='Verify the new live adapter and virtual navigation, no EEG')
    parser.add_argument('--software-run',default='hdmi_candidate_20261008')
    args = parser.parse_args()
    SLEEP_TRACE=args.sleep_trace
    NATIVE_SCAN=args.native_scan
    INTEGRATED=args.integrated;SOFTWARE_RUN=args.software_run
    if not SOFTWARE_RUN.startswith('hdmi_candidate_20261008') or '/' in SOFTWARE_RUN or '\\' in SOFTWARE_RUN:
        raise ValueError('Unexpected software bundle directory')
    if INTEGRATED and not NATIVE_SCAN:raise ValueError('Integration requires a native nonflashing stage')
    if NATIVE_SCAN and (args.mode!='dynamic_nonflashing' or not args.run_id or SLEEP_TRACE):
        raise ValueError('Native scan requires a fresh isolated nonflashing stage without preload diagnostics')
    if SLEEP_TRACE and (args.mode!='dynamic_nonflashing' or not args.run_id):
        raise ValueError('Sleep diagnostics require a new isolated nonflashing stage')
    if args.mode=='dynamic_nonflashing':
        OUT=ROOT/'output/dynamic_latch_20261008';LAUNCH=OUT/'launch.json'
    if args.run_id:
        if not args.run_id.isascii() or not all(c.isalnum() or c=='-' for c in args.run_id):
            raise ValueError('Evidence suffix must be ASCII letters/digits/hyphens')
        OUT=OUT.with_name(OUT.name+'-'+args.run_id);LAUNCH=OUT/'launch.json'
    media = json.loads(board.STATE.read_text())
    client = board.upload.trial.connect("192.168.2.99")
    try:
        globals()[args.action](client, media)
    finally:
        client.close()
