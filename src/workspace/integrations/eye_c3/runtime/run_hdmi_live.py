"""Stage and operate a finite, recoverable HDMI/real-EEG test without /etc edits."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import stat
import uuid

import run_live_system as board

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/hdmi_live_20261008'
STATE = OUT / 'state.json'
FORMAL = '/home/xilinx/jupyter_notebooks/guardianloop_pynq'
USER_CONTROLLED = False


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def stage(client, media):
    if STATE.exists():
        raise ValueError('Retained live stage exists; inspect it')
    before = board.audit(client, media)
    if not before['release_unchanged'] or before['pl'] != media['original_overlay']:
        raise ValueError('Formal release/PL changed')
    package = json.loads((ROOT / 'output/hdmi_candidate_20261008-native-stream/stage.json').read_text())
    remote = '/home/xilinx/gl-hdmi-live-20261008-' + uuid.uuid4().hex[:8]
    save('last-stage-target.json',dict(remote=remote,hardware_changed=False))
    board.execute(client, shlex.join(['mkdir', '-m', '700', remote]))
    with client.open_sftp() as ftp:
        names = [e.filename for e in ftp.listdir_attr(media['remote'])
            if stat.S_ISREG(e.st_mode) and Path(e.filename).suffix in ('.py','.html','.js','.so','.npz')]
    board.execute(client, shlex.join(['cp', '--', *[media['remote']+'/'+n for n in names], remote]), True)
    board.execute(client, shlex.join(['chown','xilinx:xilinx',*[remote+'/'+n for n in names]]), True)
    board.execute(client, shlex.join(['mkdir', '-m', '700', remote+'/system_runtime', remote+'/assets']))
    board.execute(client, shlex.join(['cp','-a','--',package['remote']+'/guardianloop_system',remote+'/system_runtime/']))
    board.execute(client, shlex.join(['mkdir','-m','700',remote+'/system_runtime/wheelchair_ssvep']))
    board.execute(client, shlex.join(['cp','--',package['remote']+'/wheelchair_ssvep/dry_run_bridge.py',
        remote+'/system_runtime/wheelchair_ssvep/dry_run_bridge.py']))
    if board.execute(client,shlex.join(['sha256sum',remote+'/system_runtime/wheelchair_ssvep/dry_run_bridge.py'])).split()[0] != package['hashes']['wheelchair_ssvep/dry_run_bridge.py']:
        raise ValueError('Virtual direction dependency changed')
    for name in package['hashes']:
        if name.startswith('phone_video_upload/'):
            board.execute(client, shlex.join(['cp','--',package['remote']+'/'+name,remote+'/'+Path(name).name]))
    assets=board.execute(client,shlex.join(['find',media['remote']+'/assets','-mindepth','1',
        '-maxdepth','1','-type','d','-printf','%f\n']),True).splitlines()
    for name in assets:
        if name in ('sd01','sd02') or (len(name)==32 and all(c in '0123456789abcdef' for c in name)):
            board.execute(client, shlex.join(['ln','-s',media['remote']+'/assets/'+name,remote+'/assets/'+name]))
    board.execute(client, shlex.join(['cp','--',media['remote']+'/access.key',remote+'/access.key']), True)
    board.execute(client, shlex.join(['chown','xilinx:xilinx',remote+'/access.key']), True)
    release = json.loads(board.execute(client, shlex.join(['cat',FORMAL+'/release_manifest.json'])))
    pid = int(board.execute(client,shlex.join(['systemctl','show','guardianloop-cyton.service','-p','MainPID','--value'])))
    code = 'from pathlib import Path; import json; print(json.dumps([p.decode() for p in Path('+repr('/proc/%d/cmdline'%pid)+').read_bytes().split(b"\\0") if p]))'
    argv = json.loads(board.execute(client,shlex.join([board.PYTHON,'-c',code]),True))
    if argv[:2] != [board.PYTHON, FORMAL+'/guardianloop_acquisition.py']:
        raise ValueError('Unexpected formal acquisition command')
    state = dict(remote=remote,boot=before['boot'],before_pid=pid,
        formal_entry=argv[1],formal_hashes=release['files'],candidate_runtime=package['remote']+'/runtime',
        user_controlled=USER_CONTROLLED,
        module_hashes={n:package['hashes']['runtime/'+n+'.py'] for n in
            ('ssvep_free','ssvep_hdmi','ssvep_cue_runtime')})
    command = [board.PYTHON,remote+'/hdmi_live_entry.py','--state',remote+'/state.json',
               '--formal-entry',argv[1],'--',*argv[2:]]
    state['override_text'] = ('[Service]\nExecStart=\nExecStart='+shlex.join(command)+'\n'
        'Environment=PYTHONPATH='+remote+'\nEnvironment=GL_HDMI_LIVE_STATE='+remote+'/state.json\n'
        'Environment=GL_PAGE_POLICY_PATH=/dev/shm/'+Path(remote).name+'-system-page.json\n')
    media_state = dict(media,remote=remote,prefix=Path(remote).name,hdmi_candidate=True,
        ssvep_runtime=state['candidate_runtime'],ssvep_port=9105,test_seconds=480,user_controlled=USER_CONTROLLED,
        native_scan_library=package['remote']+'/phone_video_upload/libguardianloop_scan.so',
        native_scan_sha256='a3bd7664768405b212b8713fd0d79ab0a8c2634e497f5cc35a0f72087100c7fb')
    paths=(media['original_overlay'],media['original_overlay'].replace('.bit','.hwh'),
           media['display_overlay'],media['display_overlay'].replace('.bit','.hwh'))
    media_state['hardware_hashes']={p:board.execute(client,shlex.join(['sha256sum',p]),True).split()[0] for p in paths}
    with client.open_sftp() as ftp:
        for name in ('hdmi_live_entry.py','hdmi_live_session.py','test_hdmi_live_entry.py','media_server.py',
                     'media_player.py','playback_policy.py','test_playback_policy.py','test_media_server.py',
                     'system_mobile.html','system_mobile.js'):
            ftp.put(str(ROOT/name),remote+'/'+name)
            expected=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
            if board.execute(client,shlex.join(['sha256sum',remote+'/'+name])).split()[0]!=expected:
                raise ValueError('Transfer changed: '+name)
        for name, value in (('state.json',state),('media_state.json',media_state)):
            with ftp.open(remote+'/'+name,'w') as stream:
                stream.write(json.dumps(value))
            ftp.chmod(remote+'/'+name,0o600)
    save('before.json',before)
    save('state.json',state)
    env=['env','XILINX_XRT=/usr','OPENBLAS_NUM_THREADS=1','PYTHONPATH='+remote+':'+state['candidate_runtime']+
        ':'+remote+'/system_runtime:'+media['eye_root']+'/src',board.PYTHON]
    print(board.execute(client,shlex.join(env+['-c',
        'from system_hdmi import UnifiedDisplay; from guardianloop_system.live_inputs import BrainInputs; from hdmi_stimulus import HdmiStimulus; print("DISPLAY_IMPORTS_OK")']),True))
    tests=shlex.join(env+['-m','unittest','test_hdmi_live_entry','test_media_server','test_player_commands','test_playback_policy','-v'])+' 2>&1'
    _,stdout,stderr=client.exec_command(tests,timeout=120)
    output=stdout.read().decode(errors='replace')+stderr.read().decode(errors='replace')
    code=stdout.channel.recv_exit_status()
    save('software-tests.json',dict(output=output,exit_code=code));print(output)
    if code:raise RuntimeError('Temporary entry tests failed')
    preflight(client, media)


def preflight(client, media):
    state=json.loads(STATE.read_text(encoding='utf-8'))
    remote=state['remote']
    env=['env','XILINX_XRT=/usr','OPENBLAS_NUM_THREADS=1','PYTHONPATH='+remote+':'+state['candidate_runtime']+
        ':'+remote+'/system_runtime:'+media['eye_root']+'/src',board.PYTHON]
    probe=shlex.join(env+[remote+'/hdmi_live_entry.py','--state',remote+'/state.json',
        '--formal-entry',state['formal_entry'],'--preflight'])+' 2>&1'
    output=board.execute(client,probe,True)
    passed='SPAWN_PREFLIGHT_PASSED_NO_SERIAL_NO_PL' in output
    save('spawn-preflight-retry.json',dict(output=output,passed=passed,serial_opened=False,pl_loaded=False))
    print(output)
    if not passed:raise RuntimeError('Spawned real-EEG tap preflight failed; no service change made')
    save('after-preflight.json',board.audit(client,media))
    print('HDMI_LIVE_STAGE_READY_NO_SERVICE_OR_PL_CHANGE')


def activate(client, media):
    state=json.loads(STATE.read_text(encoding='utf-8'))
    if not json.loads((OUT/'spawn-preflight-retry.json').read_text())['passed']:
        raise ValueError('Spawn preflight has not passed')
    if board.audit(client,media)!=json.loads((OUT/'before.json').read_text(encoding='utf-8')):
        raise ValueError('Board changed since preflight')
    print(board.execute(client,shlex.join(['env','XILINX_XRT=/usr',board.PYTHON,
        state['remote']+'/hdmi_live_session.py','activate','--state',state['remote']+'/state.json']),True))


def request(client, body=None):
    state=json.loads(STATE.read_text(encoding='utf-8'))
    code='''import json,sys,urllib.request
from pathlib import Path
base='http://127.0.0.1:9119'
key=Path(sys.argv[1]+'/access.key').read_text().strip()
body=json.loads(sys.argv[2])
data=json.dumps(body).encode() if body is not None else None
headers={'X-Media-Key':key,'Origin':base,'Content-Type':'application/json'}
with urllib.request.urlopen(urllib.request.Request(base+'/api/player',data=data,headers=headers),timeout=3) as r:
 print(r.read().decode())
'''
    return json.loads(board.execute(client,shlex.join([board.PYTHON,'-c',code,state['remote'],json.dumps(body)])))


def status(client, media):
    state=json.loads(STATE.read_text(encoding='utf-8'))
    print(board.execute(client,shlex.join(['systemctl','show','guardianloop-cyton.service',
        Path(state['remote']).name+'-server.service','-p','MainPID','-p','ActiveState','-p','Result'])))
    value=request(client)
    save('last-status.json',value)
    print(json.dumps(dict(player=value['player'],hdmi_candidate_available=value['hdmi_candidate_available']),ensure_ascii=False))


def probe(client, media):
    code='''import json,time,urllib.request
for port,path in ((9102,'/api/status'),(9105,'/api/ssvep-hdmi')):
 with urllib.request.urlopen('http://127.0.0.1:%s%s'%(port,path),timeout=3) as r:
  row=json.load(r)
 if port==9102:
  f=row.get('fatigue',{})
  print(json.dumps({'port':port,'stale':row.get('stale'),**{k:f.get(k) for k in ('state','reason','packets_seen','sequence_gaps','malformed_bytes','calibration_current','signal_quality')}},ensure_ascii=False))
 else:
  print(json.dumps({'port':port,'policy':row.get('policy'),'control_enabled':row.get('control_enabled'),'state':row.get('state'),'reason':row.get('reason')},ensure_ascii=False))
'''
    print(board.execute(client,shlex.join([board.PYTHON,'-c',code])))


def play(client, media):
    value=request(client)
    video=next(v for v in value['videos'] if v['prepared'])
    result=request(client,dict(action='play',id=video['id']))
    save('play.json',result);print(json.dumps(result))


def restore(client, media):
    state=json.loads(STATE.read_text(encoding='utf-8'))
    print(board.execute(client,shlex.join(['env','XILINX_XRT=/usr',board.PYTHON,
        state['remote']+'/hdmi_live_session.py','restore','--state',state['remote']+'/state.json']),True))
    save('after.json',board.audit(client,media))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('stage','preflight','activate','probe','status','play','restore','command'))
    parser.add_argument('--command');parser.add_argument('--value',type=int)
    parser.add_argument('--keep-open',action='store_true')
    args=parser.parse_args()
    if args.keep_open:
        USER_CONTROLLED=True
        OUT=ROOT/'output/hdmi_live_user_controlled_20261008'
        STATE=OUT/'state.json'
    media=json.loads(board.STATE.read_text());client=board.upload.trial.connect('192.168.2.99')
    try:
        if args.action=='command':
            body={'action':args.command}
            if args.value is not None:body['value']=args.value
            print(json.dumps(request(client,body)))
        else:globals()[args.action](client,media)
    finally:client.close()
