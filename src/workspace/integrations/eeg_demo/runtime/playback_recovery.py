"""Independent recovery timer for this exact finite display unit."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import argparse

from pynq import Overlay, PL

BASE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--state', type=Path, default=BASE / 'playback_state.json')
args = parser.parse_args()
if args.state.resolve().parent != BASE:
    raise RuntimeError('Recovery state must stay within this private stage')
STATE = json.loads(args.state.read_text())
unit = STATE["hardware_unit"]
original = STATE["original_overlay"]


def run(*args):
    return subprocess.run(args, capture_output=True, text=True,
                          check=True, timeout=20).stdout.strip()


def pid():
    return int(run("systemctl", "show", unit, "-p", "MainPID", "--value"))


owner = pid()
if not owner and STATE.get('session_id'):
    report_path=BASE/(STATE['session_id']+'-report.json')
    report=json.loads(report_path.read_text()) if report_path.exists() else {}
    if report.get('original_restored') and report.get('buffers_released'):
        # A completed session's old timer must never reconfigure a newer session.
        raise SystemExit(0)
    hardware_lock=open('/run/lock/guardianloop-pl.lock','a')
    fcntl.flock(hardware_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
if owner:
    script = STATE.get('owner_script', 'display_trial.py')
    if script not in ('display_trial.py', 'media_player.py'):
        raise RuntimeError('Unrecognized recovery owner')
    expected = str(BASE / script).encode()
    if expected not in (Path("/proc") / str(owner) / "cmdline").read_bytes().split(b"\0"):
        raise RuntimeError("Timer refuses to affect an unrelated process")
    os.kill(owner, signal.SIGTERM)
    end = time.monotonic() + 8
    while pid() == owner and time.monotonic() < end:
        time.sleep(.2)

with open(BASE / "restore.lock", "a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    current = PL.bitfile_name
    if current not in (original, STATE["display_overlay"]):
        raise RuntimeError("Unexpected PL owner; recovery requires manual inspection")
    if current != original or pid():
        if hashlib.sha256(Path(original).read_bytes()).hexdigest() != STATE["hardware_hashes"][original]:
            raise RuntimeError("Original recovery bitstream changed")
        Overlay(original)
        if PL.bitfile_name != original:
            raise RuntimeError("Emergency PL restore did not verify")
    remaining = pid()
    if remaining:
        if remaining != owner:
            raise RuntimeError("Display service PID changed; refuse to kill")
        # Full reconfiguration has already stopped this display DMA.
        os.kill(remaining, signal.SIGKILL)
    run("systemctl", "start", "guardianloop-cyton.service")
    (BASE / "watchdog_report.json").write_text(json.dumps({"original_restored": True,
        "service_state": run("systemctl", "show", "guardianloop-cyton.service",
                             "-p", "ActiveState", "--value")}))
