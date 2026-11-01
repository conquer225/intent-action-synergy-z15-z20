"""Pinned private Linux tests and recorded workload; no live service/PL mutation."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex

import run_hdmi_live as live

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'phone_video_upload/output/prewear_hardening_20261008'
STATE=OUT/'stage.json'
FORMAL='/home/xilinx/jupyter_notebooks/guardianloop_pynq'
LIVE=ROOT/'phone_video_upload/output/hdmi_live_user_controlled_20261008/state.json'
FORMAL_SOURCES=('cyton_guardianloop.py','wear_session.py','ssvep_recording.py','cyton_trial_recorder.py',
                'ssvep_free.py','ssvep_hdmi.py','ssvep_cue_runtime.py')
MEDIA_SOURCES=('media_server.py','media_player.py','prewear.py','hdmi_stimulus.py',
               'system_mobile.js','system_mobile.html','hdmi_live_session.py','hdmi_boot.py')
SYSTEM_SOURCES=('core.py','live_inputs.py','test_core.py','test_live_inputs.py')
TESTS=('test_wear_session','test_calibration_main','test_primary_stream_recovery','test_calibration_session',
       'test_ssvep_recording','test_ssvep_hdmi','test_ssvep_cue_runtime','test_ssvep_free',
       'test_prewear','test_media_server','test_player_commands','test_hdmi_stimulus','test_hdmi_boot',
       'guardianloop_system.test_core','guardianloop_system.test_live_inputs')


def stage(client):
    if STATE.exists():raise ValueError('Existing private stage; inspect it')
    current=json.loads(LIVE.read_text());base=current['remote']
    remote=live.board.execute(client,'mktemp -d /home/xilinx/gl-prewear-20261008-XXXXXX').strip()
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'last-stage-target.json').write_text(json.dumps(dict(remote=remote,live_changed=False)))
    code='''import hashlib,json,pathlib,shutil,sys
formal=pathlib.Path(sys.argv[1]);base=pathlib.Path(sys.argv[2]);stage=pathlib.Path(sys.argv[3]);runtime=stage/'runtime';runtime.mkdir()
manifest=json.loads((formal/'release_manifest.json').read_text())
for n,h in manifest['files'].items():
 if pathlib.Path(n).name!=n or hashlib.sha256((formal/n).read_bytes()).hexdigest()!=h:raise ValueError('Release changed')
 shutil.copy2(formal/n,runtime/n)
for p in base.iterdir():
 if p.is_file() and p.suffix=='.py':shutil.copy2(p,runtime/p.name)
shutil.copytree(base/'system_runtime',runtime/'system_runtime',ignore=shutil.ignore_patterns('__pycache__'))
fixture=pathlib.Path('/home/xilinx/gl-media-20261007-314e8796/replay_runtime/bench_input.npz')
if hashlib.sha256(fixture.read_bytes()).hexdigest()!='fb090903dbb523f8bed746ebbe95f4dc26dd70b0c2ab9ad04f716b46fbfcef6f':raise ValueError('Fixture changed')
shutil.copy2(fixture,runtime/'bench_input.npz')
print('PRIVATE_CHECKSUMMED_COPY_NO_USB_NO_PL')
'''
    print(live.board.execute(client,shlex.join([live.board.PYTHON,'-c',code,FORMAL,base,remote])))
    STATE.write_text(json.dumps(dict(remote=remote,live=base,current=current),indent=2))
    refresh(client)


def refresh(client):
    state=json.loads(STATE.read_text());remote=state['remote']
    pairs=[(ROOT/'pynq_guardianloop'/n,'runtime/'+n) for n in FORMAL_SOURCES]
    pairs += [(ROOT/'phone_video_upload'/n,'runtime/'+n) for n in MEDIA_SOURCES]
    pairs += [(ROOT/'guardianloop_system'/n,'runtime/system_runtime/guardianloop_system/'+n) for n in SYSTEM_SOURCES]
    for name in TESTS:
        if name.startswith('guardianloop_system.'):continue
        folder='pynq_guardianloop' if (ROOT/'pynq_guardianloop'/(name+'.py')).exists() else 'phone_video_upload'
        pairs.append((ROOT/folder/(name+'.py'),'runtime/'+name+'.py'))
    for name in ('soak_service_replay.py','mi_multitask_replay.py','replay_release_audit.py',
                 'replay_stage_trace.py','mi_worker_audit.py','audited_seed_shadow.py','test_cyton_reader_faults.py',
                 'page_scheduled_replay.py','test_replay_covariance.py'):
        pairs.append((ROOT/'pynq_guardianloop'/name,'runtime/'+name))
    hashes={}
    with client.open_sftp() as ftp:
        for source,relative in pairs:
            ftp.put(str(source),remote+'/'+relative)
            hashes[relative]=hashlib.sha256(source.read_bytes()).hexdigest()
    code='import hashlib,json,pathlib,sys; r=pathlib.Path(sys.argv[1]); h=json.loads(sys.argv[2]); assert all(hashlib.sha256((r/n).read_bytes()).hexdigest()==d for n,d in h.items()); print("TRANSFER_VERIFIED")'
    print(live.board.execute(client,shlex.join([live.board.PYTHON,'-c',code,remote,json.dumps(hashes)])))
    OUT.mkdir(parents=True,exist_ok=True)
    state['hashes']=hashes;STATE.write_text(json.dumps(state,indent=2))


def tests(client):
    state=json.loads(STATE.read_text());runtime=state['remote']+'/runtime'
    code="import sys,unittest; r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:]));sys.exit(not r.wasSuccessful())"
    command=shlex.join(['env','XILINX_XRT=/usr','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1',
        'GL_TEST_FATIGUE_MODEL='+runtime+'/cyton_fatigue_overlap4.json',
        'GL_TEST_EYE_ROOT=/home/xilinx/brain_eye_coexist_20261005/eye',
        'PYTHONPATH='+runtime+':'+runtime+'/system_runtime:/home/xilinx/brain_eye_coexist_20261005/eye/src',live.board.PYTHON,'-c',code,*TESTS])
    stdin,stdout,stderr=client.exec_command(command+' 2>&1',timeout=300)
    output=stdout.read().decode(errors='replace')+stderr.read().decode(errors='replace')
    result=dict(exit_code=stdout.channel.recv_exit_status(),output=output,raw_usb_opened=False,pl_loaded=False)
    (OUT/'linux-tests.json').write_text(json.dumps(result,indent=2))
    print(output)
    if result['exit_code']:raise RuntimeError('Linux private tests failed; production unchanged')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('stage','refresh','tests'))
    args=parser.parse_args();client=live.board.upload.trial.connect('192.168.2.99')
    try:globals()[args.action](client)
    finally:client.close()
