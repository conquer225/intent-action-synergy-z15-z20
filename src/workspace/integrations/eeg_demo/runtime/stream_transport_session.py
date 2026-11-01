"""Board-local pure-receive check, requiring an automatic service recovery hook."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from guardianloop_startup import verify_files
from cyton_trial_recorder import STATUS_PATH, read_json


def main():
    stage = Path(__file__).resolve().parent
    plan = json.loads((stage/'plan.json').read_text())
    root = Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
    unit = plan['unit'] + '.service'
    if not os.environ.get('INVOCATION_ID') or os.environ.get('GL_TRANSPORT_UNIT') != unit:
        raise ValueError('Run only through the recovery-protected transient unit')
    restore = subprocess.check_output(['systemctl', 'show', unit, '-p', 'ExecStopPost', '--value'],
                                      text=True, timeout=10)
    if 'argv[]=/bin/systemctl start guardianloop-cyton.service' not in restore:
        raise ValueError('Automatic acquisition recovery is absent')
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != plan['boot']:
        raise ValueError('Boot changed')
    for path, expected in plan['protected'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Protected artifact changed: ' + path)
    manifest = json.loads((root/'release_manifest.json').read_text())
    verify_files(root, manifest)
    if read_json(STATUS_PATH).get('state') == 'recording':
        raise ValueError('Do not interrupt a recording')
    running = subprocess.check_output(['systemctl', 'show', 'guardianloop-cyton.service',
                                      '-p', 'MainPID', '--value'], text=True, timeout=10).strip()
    if running != str(plan['acquisition_pid']):
        raise ValueError('Acquisition process changed before suspension')
    users = subprocess.run(['fuser', plan['port']], capture_output=True, text=True, check=False)
    if users.returncode != 0 or not users.stdout.split():
        raise ValueError('Cannot establish the original serial owner')
    owner = Path('/proc/'+running+'/cgroup').read_text()
    if any(Path('/proc/'+pid+'/cgroup').read_text() != owner for pid in users.stdout.split()):
        raise ValueError('Another service owns the serial device')
    preserve = subprocess.check_output(['systemctl', 'show', 'guardianloop-cyton.service',
                                       '-p', 'RuntimeDirectoryPreserve', '--value'],
                                      text=True, timeout=10).strip()
    if preserve != 'yes':
        raise ValueError('Calibration directory is not preserved')
    print('PURE_RECEIVE_BEGIN: stopping only guardianloop-cyton.service', flush=True)
    subprocess.run(['systemctl', 'stop', 'guardianloop-cyton.service'], check=True, timeout=50)
    users = subprocess.run(['fuser', plan['port']], capture_output=True, text=True, check=False)
    if users.returncode != 1 or users.stdout.strip():
        raise ValueError('Serial device was not released')
    # Imports on this ARM board took ~17 s; leave the full 40 s after startup.
    command = ['/usr/bin/timeout', '--signal=INT', '--kill-after=3s', '75s', sys.executable,
               str(stage/'diagnose_stream_transport.py'), '--port', plan['port'], '--seconds', '40']
    measured = subprocess.run(command, capture_output=True, text=True, check=False)
    print('PURE_RECEIVE_REPORT: ' + json.dumps({'exit_code': measured.returncode,
          'stdout': measured.stdout, 'stderr': measured.stderr}), flush=True)
    if measured.returncode:
        raise RuntimeError('Pure receive did not complete; automatic recovery will run')


if __name__ == '__main__':
    main()
