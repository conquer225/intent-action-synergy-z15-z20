"""Stage and verify the 11 October input repair before recoverable installation."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import secrets
import shlex
import stat

import run_hdmi_live as live

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'phone_video_upload/output/input_repair_20261011'
STATE=OUT/'stage.json'
FORMAL='/home/xilinx/jupyter_notebooks/guardianloop_pynq'
BASE='/home/xilinx/gl-hdmi-live-20261008-ea117349'
CANDIDATE='/home/xilinx/gl-hdmi-software-20261008-6797e092/runtime'
EYE='/home/xilinx/brain_eye_coexist_20261005/eye/src/coexist_guard.py'
PAGE_TIMING_ONLY=False
PREWEAR_ISSUES_ONLY=False
DISPLAY_SOURCE=ROOT/'phone_video_upload/media_player.py'
SOURCES={'cyton_guardianloop.py':ROOT/'pynq_guardianloop/cyton_guardianloop.py',
    'cyton_reader_sink.py':ROOT/'pynq_guardianloop/cyton_reader_sink.py',
    'cyton_sqi.py':ROOT/'pynq_guardianloop/cyton_sqi.py',
    'mi_acquisition.py':OUT/'candidate/mi_acquisition.py',
    'ssvep_acquisition.py':ROOT/'pynq_guardianloop/ssvep_acquisition.py',
    'ssvep_cue_runtime.py':ROOT/'pynq_guardianloop/ssvep_cue_runtime.py',
    'page_policy.py':ROOT/'guardianloop_system/page_policy.py',
    'guardianloop_web.py':ROOT/'pynq_guardianloop/guardianloop_web.py',
    'ssvep_free.html':ROOT/'pynq_guardianloop/ssvep_free.html',
    'ssvep_input_prepare.js':ROOT/'pynq_guardianloop/ssvep_input_prepare.js'}
TESTS=('test_cyton_sqi','test_page_policy','test_ssvep_cue_runtime','test_ssvep_acquisition',
       'test_primary_windows','test_mi_reader_tap','test_mi_tap_batch','test_calibration_session',
       'test_calibration_installer')


def digest(data):return hashlib.sha256(data).hexdigest()


def execute(client,argv):return live.board.execute(client,shlex.join(argv),True)


def read(client,path):
    with client.open_sftp() as ftp:
        try:
            with ftp.open(path,'rb') as f:return f.read()
        except PermissionError:
            return base64.b64decode(execute(client,['base64','-w0',path]))


def save(name,value):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(value,indent=2),encoding='utf-8')


def stage(client):
    if STATE.exists():
        old=json.loads(STATE.read_text())
        status=execute(client,['systemctl','show',old['unit']+'.service','-p','ActiveState','--value']).strip()
        if status not in ('inactive','failed'):raise ValueError('Never overwrite a running private test')
        remote=old['remote']
    else:
        remote=live.board.execute(client,'mktemp -d /home/xilinx/gl-calibration-install-20261011-XXXXXX').strip()
    manifest=json.loads(read(client,FORMAL+'/release_manifest.json'))
    hashes={name:digest(path.read_bytes()) for name,path in SOURCES.items()}
    display_hash=digest(DISPLAY_SOURCE.read_bytes()) if PAGE_TIMING_ONLY else None
    code="""from pathlib import Path
import json,shutil,sys,hashlib,os
root=Path(sys.argv[1]);stage=Path(sys.argv[2]);m=json.loads((root/'release_manifest.json').read_text())
runtime=stage/'runtime';runtime.mkdir(mode=0o700,exist_ok=True);owner=stage.stat()
os.chown(runtime,owner.st_uid,owner.st_gid)
for name,expected in m['files'].items():
 p=root/name
 if Path(name).name!=name or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:raise ValueError('Release differs')
 target=runtime/name;shutil.copyfile(p,target);target.chmod(0o600);os.chown(target,owner.st_uid,owner.st_gid)
"""
    execute(client,[live.board.PYTHON,'-c',code,FORMAL,remote])
    with client.open_sftp() as ftp:
        for name,path in SOURCES.items():ftp.put(str(path),remote+'/runtime/'+name)
        for module in TESTS:
            path=ROOT/('guardianloop_system' if module=='test_page_policy' else 'pynq_guardianloop')/(module+'.py')
            ftp.put(str(path),remote+'/runtime/'+module+'.py')
        for name in ('test_mi_cued.py','test_small_batch.py','test_primary_stream_recovery.py','test_ssvep_cue_runtime.py',
                     'page_scheduled_replay.py','install_calibration_repair.py'):
            ftp.put(str(ROOT/'pynq_guardianloop'/name),remote+'/runtime/'+name)
        ftp.put(str(ROOT/'pynq_guardianloop/install_calibration_repair.py'),remote+'/install_calibration_repair.py')
        if PAGE_TIMING_ONLY:
            ftp.put(str(DISPLAY_SOURCE),remote+'/runtime/media_player.py')
    # The test imports the package name as well as the installed flat module.
    execute(client,['ln','-sfn','.',remote+'/runtime/guardianloop_system'])
    execute(client,['ln','-sfn','.',remote+'/runtime/pynq_guardianloop'])
    unit=Path(remote).name+'-tests-'+secrets.token_hex(2)
    save('stage.json',dict(remote=remote,hashes=hashes,unit=unit,previous_release=manifest['release_id'],
                           display_hash=display_hash))
    if PAGE_TIMING_ONLY:
        execute(client,[live.board.PYTHON,'-m','py_compile',remote+'/runtime/media_player.py'])
    print(execute(client,['systemd-run','--unit='+unit,'--property=RuntimeMaxSec=180',
        '--property=Nice='+('0' if PAGE_TIMING_ONLY or PREWEAR_ISSUES_ONLY else '10'),'--property=TimeoutStopSec=10','env','XILINX_XRT=/usr',
        'OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','PYTHONPATH='+remote+'/runtime',
        'GL_TEST_FATIGUE_MODEL='+remote+'/runtime/cyton_fatigue_overlap4.json',
        live.board.PYTHON,'-m','unittest',*TESTS,'-q']))
    print('PRIVATE_TESTS_STARTED_NO_FORMAL_CHANGE',remote)


def tests(client):
    s=json.loads(STATE.read_text())
    result=execute(client,['systemctl','show',s['unit']+'.service','-p','ActiveState','-p','Result','-p','ExecMainStatus'])
    log=execute(client,['journalctl','-u',s['unit']+'.service','--no-pager','-n','45','-o','cat'])
    save('linux-tests.json',dict(result=result,log=log,passed='ActiveState=inactive' in result
        and 'Result=success' in result and 'ExecMainStatus=0' in result and '\nOK' in log))
    print(result);print(log)


def plan(client, release_id=None):
    if release_id is not None and not re.fullmatch(r'guardianloop-[a-z0-9-]{1,80}', release_id):
        raise ValueError('Invalid repair release identity')
    s=json.loads(STATE.read_text())
    if not json.loads((OUT/'linux-tests.json').read_text())['passed']:raise ValueError('Board tests not passed')
    if any(digest(p.read_bytes())!=s['hashes'][n] for n,p in SOURCES.items()):raise ValueError('Source changed after tests')
    if PAGE_TIMING_ONLY and digest(DISPLAY_SOURCE.read_bytes())!=s['display_hash']:
        raise ValueError('Display source changed after checks')
    raw=read(client,FORMAL+'/release_manifest.json');manifest=json.loads(raw)
    current=json.loads(read(client,BASE+'/state.json'))
    if current['formal_hashes']!=manifest['files']:raise ValueError('Live wrapper does not match formal release')
    boot=execute(client,['cat','/proc/sys/kernel/random/boot_id']).strip()
    if boot!=current['boot']:raise ValueError('Boot changed')
    player=json.loads(read(client,BASE+'/player_status.json'))
    ident=player['session_id']
    if not re.fullmatch('play-[a-f0-9]{8}',ident):raise ValueError('Foreign player')
    p=dict(live=BASE,input_repair_update=True,page_timing_update=PAGE_TIMING_ONLY,
           prewear_issue_update=PREWEAR_ISSUES_ONLY,
           boot=boot,tests_passed=True,files=[],
           previous_manifest_sha=digest(raw),display_unit=ident+'.service',
           web_services=['guardianloop-web.service',Path(BASE).name+'-server.service'])
    payload=OUT/'payload';payload.mkdir(exist_ok=True)
    with client.open_sftp() as ftp:
        def add(target,data,mode=0o644):
            try:
                info=ftp.lstat(target)
                if stat.S_ISLNK(info.st_mode):raise ValueError('Linked target')
                old=read(client,target);old_sha=digest(old);old_mode=stat.S_IMODE(info.st_mode)
                (OUT/('before-'+Path(target).name)).write_bytes(old)
            except FileNotFoundError:old_sha=old_mode=None
            key='%02d-%s'%(len(p['files']),Path(target).name)
            (payload/key).write_bytes(data)
            p['files'].append(dict(target=target,key=key,old_sha=old_sha,old_mode=old_mode,
                                   new_sha=digest(data),new_mode=mode))
        for name,path in SOURCES.items():
            data=path.read_bytes();add(FORMAL+'/'+name,data);manifest['files'][name]=digest(data)
        if PAGE_TIMING_ONLY:add(BASE+'/media_player.py',DISPLAY_SOURCE.read_bytes())
        manifest['previous_release_id']=manifest['release_id']
        manifest['release_id']=('guardianloop-prewear-issues-repair-20261011' if PREWEAR_ISSUES_ONLY else
                                'guardianloop-page-timing-repair-20261011' if PAGE_TIMING_ONLY else
                                'guardianloop-fixed8-input-repair-20261011')
        if release_id is not None:manifest['release_id']=release_id
        manifest['load_relief'].update(ssvep_schedule='HDMI_drive_or_explicit_browser_input_lease',
            reader_tap_batch_samples=10,live_HDMI_acceptance=False)
        if PAGE_TIMING_ONLY:
            manifest['load_relief']['page_lease_clock']='read_then_sample_monotonic'
        if PREWEAR_ISSUES_ONLY:
            manifest['load_relief'].update(web_status_query='single_fresh_service_query_fixed_receiver',
                primary_window_timing='worker_wall_clock_not_input_age')
        encoded=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')
        add(FORMAL+'/release_manifest.json',encoded)
        guard=read(client,EYE).decode()
        guard,n=re.subn(r"PRIMARY_MANIFEST = '[a-f0-9]{64}'","PRIMARY_MANIFEST = '"+digest(encoded)+"'",guard)
        if n!=1:raise ValueError('Unexpected guard')
        add(EYE,guard.encode())
        startup=json.loads(read(client,'/run/guardianloop-startup/status.json'))
        if startup['state']!='ready' or startup['boot_id']!=boot:raise ValueError('Startup contract changed')
        startup.update(release_id=manifest['release_id'],verified_files=len(manifest['files']),
                       calibration_recovery='same_boot_and_same_models_only')
        # This public boot report is also read by the unprivileged web service.
        add('/run/guardianloop-startup/status.json',json.dumps(startup,indent=2).encode(),0o644)
        current['formal_hashes']=manifest['files']
        if 'ssvep_cue_runtime.py' in SOURCES:
            current['module_hashes']['ssvep_cue_runtime']=s['hashes']['ssvep_cue_runtime.py']
        add(BASE+'/state.json',json.dumps(current,indent=2).encode(),0o600)
        if 'ssvep_cue_runtime.py' in SOURCES:
            add(CANDIDATE+'/ssvep_cue_runtime.py',SOURCES['ssvep_cue_runtime.py'].read_bytes())
        pins=json.loads(read(client,BASE+'/boot-pins.json'))
        pins['manifest_sha256']=digest(encoded)
        for name,d in manifest['files'].items():pins['files'][FORMAL+'/'+name]=d
        for row in p['files']:
            if row['target'] not in (BASE+'/state.json','/run/guardianloop-startup/status.json'):
                pins['files'][row['target']]=row['new_sha']
        add(BASE+'/boot-pins.json',json.dumps(pins,indent=2).encode(),0o600)
        ftp.mkdir(s['remote']+'/payload',mode=0o700)
        for row in p['files']:ftp.put(str(payload/row['key']),s['remote']+'/payload/'+row['key'])
        save('deployment-plan.json',p)
        ftp.put(str(OUT/'deployment-plan.json'),s['remote']+'/deployment-plan.json')
        ftp.chmod(s['remote']+'/deployment-plan.json',0o600)
    print('RECOVERABLE_PLAN_READY',len(p['files']),digest(encoded))


def run(client,action):
    s=json.loads(STATE.read_text())
    print(execute(client,['env','XILINX_XRT=/usr','OPENBLAS_NUM_THREADS=1',live.board.PYTHON,
                         s['remote']+'/install_calibration_repair.py',action]))
    if action in ('commit','rollback'):
        current=json.loads(read(client,BASE+'/state.json'))
        (ROOT/'phone_video_upload/output/hdmi_live_user_controlled_20261008/state.json').write_text(json.dumps(current,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('stage','tests','plan','install','commit','rollback'))
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--page-timing-only',action='store_true')
    modes.add_argument('--prewear-issues-only',action='store_true')
    args=parser.parse_args()
    if args.page_timing_only:
        PAGE_TIMING_ONLY=True
        OUT=ROOT/'phone_video_upload/output/page_timing_repair_20261011';STATE=OUT/'stage.json'
        SOURCES={'page_policy.py':ROOT/'guardianloop_system/page_policy.py'}
        TESTS=('test_page_policy','test_calibration_installer')
    if args.prewear_issues_only:
        PREWEAR_ISSUES_ONLY=True
        OUT=ROOT/'phone_video_upload/output/prewear_issues_install_20261011';STATE=OUT/'stage.json'
        SOURCES={name:ROOT/'pynq_guardianloop'/name for name in
                 ('guardianloop_web.py','mobile.js','async_primary.py','cyton_guardianloop.py')}
        TESTS=('test_web_system_status','test_seed_shadow_web','test_mobile_web','test_cyton_sqi',
               'test_calibration_session','test_async_primary','test_async_primary_checkpoint',
               'test_calibration_main','test_primary_stream_recovery','test_cyton_reader_faults',
               'test_small_batch','test_page_policy','test_calibration_installer')
    client=live.board.upload.trial.connect('192.168.2.99')
    try:
        if args.action in ('stage','tests','plan'):globals()[args.action](client)
        else:run(client,args.action)
    finally:client.close()
