"""Private same-release EEG workload; no USB, production status writes or actuators."""
import hashlib
import json
from pathlib import Path
import shlex

import stage_server as upload
from stage_media import ROOT,STATE,PYTHON


def main():
    state=json.loads(STATE.read_text());remote=state['remote'];target=remote+'/replay_runtime'
    c=upload.trial.connect('192.168.2.99')
    try:
        manifest=json.loads(upload.trial.execute(c,'cat /home/xilinx/jupyter_notebooks/guardianloop_pynq/release_manifest.json'))
        upload.trial.execute(c,'mkdir -m 700 '+shlex.quote(target))
        sources=ROOT.parent/'pynq_guardianloop'
        with c.open_sftp() as sftp:
            for name,sha in manifest['files'].items():
                original='/home/xilinx/jupyter_notebooks/guardianloop_pynq/'+name
                if Path(name).name!=name:raise ValueError('Unsafe release name')
                upload.trial.execute(c,'cp -p -- '+shlex.quote(original)+' '+shlex.quote(target+'/'+name),root=True)
                if upload.trial.execute(c,'sha256sum '+shlex.quote(target+'/'+name),root=True).split()[0]!=sha:
                    raise ValueError('Copied production artifact differs')
            for name in ('soak_service_replay.py','mi_multitask_replay.py','replay_release_audit.py',
                         'replay_stage_trace.py','mi_worker_audit.py'):
                sftp.put(str(sources/name),target+'/'+name);sftp.chmod(target+'/'+name,0o600)
                if upload.trial.execute(c,'sha256sum '+shlex.quote(target+'/'+name)).split()[0]!=hashlib.sha256((sources/name).read_bytes()).hexdigest():
                    raise ValueError('Replay harness transfer mismatch')
            fixture=ROOT.parent/'eeg_apps_z15/output/accepted_bench_load_20260927/bench_input.npz'
            if hashlib.sha256(fixture.read_bytes()).hexdigest()!='fb090903dbb523f8bed746ebbe95f4dc26dd70b0c2ab9ad04f716b46fbfcef6f':
                raise ValueError('Recorded workload hash mismatch')
            sftp.put(str(fixture),target+'/bench_input.npz')
        state['replay_runtime']=target
        state['replay_copied_release']=manifest['release_id']
        STATE.write_text(json.dumps(state,indent=2))
        print('SAME_RELEASE_RECORDED_WORKLOAD_STAGED',manifest['release_id'],flush=True)
    finally:c.close()


if __name__=='__main__':main()
