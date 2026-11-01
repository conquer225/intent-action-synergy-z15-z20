"""Stage the repair for Linux fault tests, before changing live acquisition."""
import hashlib
import json
from pathlib import Path
import shlex

import run_hdmi_live as live

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'phone_video_upload/output/calibration_recovery_20261008'
STATE = OUT / 'stage.json'
FORMAL = '/home/xilinx/jupyter_notebooks/guardianloop_pynq'
SOURCES = ('cyton_guardianloop.py', 'cyton_fatigue.py', 'calibration_session.py',
           'cyton_sqi.py', 'seed_replay_check.py', 'seed_quality_runtime.py')
TESTS = ('test_primary_stream_recovery.py', 'test_calibration_session.py', 'test_calibration_main.py',
         'test_cyton_wait_service.py', 'test_cyton_reader_faults.py', 'test_cyton_sqi.py')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    client = live.board.upload.trial.connect('192.168.2.99')
    try:
        if STATE.exists():
            state = json.loads(STATE.read_text())
        else:
            remote = live.board.execute(client, 'mktemp -d /home/xilinx/gl-calibration-repair-20261008-XXXXXX').strip()
            state = dict(remote=remote, formal=FORMAL)
            STATE.write_text(json.dumps(state, indent=2))
            code = '''import hashlib,json,pathlib,shutil,sys
formal=pathlib.Path(sys.argv[1]);stage=pathlib.Path(sys.argv[2]);runtime=stage/'runtime';runtime.mkdir()
manifest=json.loads((formal/'release_manifest.json').read_text())
for name,digest in manifest['files'].items():
 if pathlib.Path(name).name!=name:raise ValueError('Unsafe formal name')
 if hashlib.sha256((formal/name).read_bytes()).hexdigest()!=digest:raise ValueError('Formal file changed')
 shutil.copy2(formal/name,runtime/name)
shutil.copy2(formal/'release_manifest.json',stage/'original-manifest.json')
print('VERIFIED_PRIVATE_RUNTIME_COPY')
'''
            print(live.board.execute(client, shlex.join([live.board.PYTHON, '-c', code, FORMAL, remote])))
        remote = state['remote']
        hashes = {}
        with client.open_sftp() as ftp:
            for name in SOURCES + TESTS:
                source = ROOT / 'pynq_guardianloop' / name
                hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
                ftp.put(str(source), remote + '/runtime/' + name)
                if live.board.execute(client, shlex.join(['sha256sum', remote + '/runtime/' + name])).split()[0] != hashes[name]:
                    raise ValueError('Repair transfer changed: ' + name)
        state['hashes'] = hashes
        STATE.write_text(json.dumps(state, indent=2))
        with client.open_sftp() as ftp:
            ftp.put(str(STATE), remote + '/stage.json')
        code = "import sys;sys.path.insert(0,sys.argv[1]);import unittest;names=sys.argv[2:];r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names));sys.exit(not r.wasSuccessful())"
        env = ['env', 'XILINX_XRT=/usr', 'OPENBLAS_NUM_THREADS=1',
               'GL_TEST_FATIGUE_MODEL=' + remote + '/runtime/cyton_fatigue_overlap4.json', live.board.PYTHON]
        command = shlex.join(env + ['-c', code, remote + '/runtime', *[Path(n).stem for n in TESTS]])
        stdin, stdout, stderr = client.exec_command(command + ' 2>&1', timeout=300)
        output = stdout.read().decode(errors='replace') + stderr.read().decode(errors='replace')
        result = dict(exit_code=stdout.channel.recv_exit_status(), output=output, raw_usb_opened=False, pl_changed=False)
        (OUT / 'linux-tests.json').write_text(json.dumps(result, indent=2))
        print(output)
        if result['exit_code']:
            raise RuntimeError('Repair fault tests failed; live code unchanged')
        print('REPAIR_TESTS_PASSED_NO_LIVE_CHANGES')
    finally:
        client.close()


if __name__ == '__main__':
    main()
