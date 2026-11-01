"""Stage a separate software test bundle; never deploy services, PL or flashing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import uuid

import run_live_system as board

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'phone_video_upload/output/hdmi_candidate_20261008'
MANIFEST=OUT/'stage.json'
TESTS=('test_ssvep_hdmi','test_ssvep_free','test_ssvep_cue_runtime','test_hdmi_stimulus',
       'test_native_scan',
       'test_system_hdmi','test_scan_timing_probe','test_media_server','test_player_commands',
       'guardianloop_system.test_core','guardianloop_system.test_live_inputs',
       'guardianloop_system.test_eye_entry','wheelchair_ssvep.test_bridge')


def local_files():
    files={}
    for name in ('ssvep_free.py','ssvep_hdmi.py','ssvep_cue_runtime.py',
                 'test_ssvep_hdmi.py','test_ssvep_cue_runtime.py','test_ssvep_free.py'):
        files['runtime/'+name]=ROOT/'pynq_guardianloop'/name
    for folder in ('guardianloop_system','wheelchair_ssvep'):
        for local in (ROOT/folder).glob('*.py'):files[folder+'/'+local.name]=local
    for name in ('hdmi_stimulus.py','system_hdmi.py','test_hdmi_stimulus.py',
                 'native_scan.c','native_scan.py','test_native_scan.py',
                 'benchmark_hdmi_patches.py','media_player.py','media_server.py',
                 'player_commands.py','test_player_commands.py','test_media_server.py',
                 'test_system_hdmi.py','test_scan_timing_probe.py','scan_timing_probe.py',
                 'chunk_cache.py','bench_decoder.py','prepare_chunks.py','upload_server.py',
                 'system_mobile.html','system_mobile.js','test_system_mobile.js'):
        files['phone_video_upload/'+name]=ROOT/'phone_video_upload'/name
    for local in files.values():
        if not local.is_file():raise FileNotFoundError(local)
    return files


def save(name,value):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')


def stage(client,media):
    if MANIFEST.exists():raise ValueError('Existing software stage retained; inspect or check it')
    before=board.audit(client,media)
    if not before['release_unchanged'] or before['pl']!=media['original_overlay']:
        raise ValueError('Formal admission changed')
    remote='/home/xilinx/gl-hdmi-software-20261008-'+uuid.uuid4().hex[:8]
    board.execute(client,shlex.join(['mkdir','-m','700',remote]))
    for folder in ('runtime','phone_video_upload','guardianloop_system','wheelchair_ssvep'):
        board.execute(client,shlex.join(['mkdir','-m','700',remote+'/'+folder]))
    hashes={}
    with client.open_sftp() as ftp:
        formal='/home/xilinx/jupyter_notebooks/guardianloop_pynq'
        for entry in ftp.listdir_attr(formal):
            if stat.S_ISREG(entry.st_mode) and (entry.filename.endswith(('.py','.html','.js')) or
                    entry.filename in ('ssvep_causal_protocol.json','ssvep_candidate_sos.npy')):
                with ftp.open(formal+'/'+entry.filename,'rb') as source:raw=source.read()
                target=remote+'/runtime/'+entry.filename
                with ftp.open(target,'wb') as destination:destination.write(raw)
                ftp.chmod(target,0o600)
                hashes['runtime/'+entry.filename]=hashlib.sha256(raw).hexdigest()
        for name,local in local_files().items():
            target=remote+'/'+name;ftp.put(str(local),target);ftp.chmod(target,0o600)
            hashes[name]=hashlib.sha256(local.read_bytes()).hexdigest()
        for name,expected in hashes.items():
            actual=board.execute(client,shlex.join(['sha256sum',remote+'/'+name])).split()[0]
            if actual!=expected:raise ValueError('Software stage transfer mismatch: '+name)
    save('before.json',before)
    save('stage.json',dict(remote=remote,hashes=hashes,software_only=True,
        deployed_to_formal=False,pl_loads=0,eye_root=media['eye_root']))
    print('SEPARATE_SOFTWARE_CANDIDATE_STAGED_NO_DISPLAY_OR_SERVICE_CHANGE',remote)


def complete_assets(client,media):
    info=json.loads(MANIFEST.read_text(encoding='utf-8'))
    formal='/home/xilinx/jupyter_notebooks/guardianloop_pynq'
    if board.audit(client,media)!=json.loads((OUT/'before.json').read_text(encoding='utf-8')):
        raise ValueError('Formal admission changed')
    save('board-tests-before-assets.json',json.loads((OUT/'board-tests.json').read_text(encoding='utf-8')))
    with client.open_sftp() as ftp:
        for entry in ftp.listdir_attr(formal):
            if not stat.S_ISREG(entry.st_mode) or not entry.filename.endswith(('.html','.js')):continue
            name='runtime/'+entry.filename
            if name in info['hashes']:continue
            with ftp.open(formal+'/'+entry.filename,'rb') as stream:raw=stream.read()
            target=info['remote']+'/'+name
            with ftp.open(target,'wb') as stream:stream.write(raw)
            ftp.chmod(target,0o600)
            expected=hashlib.sha256(raw).hexdigest()
            if board.execute(client,shlex.join(['sha256sum',target])).split()[0]!=expected:
                raise ValueError('Page asset transfer mismatch')
            info['hashes'][name]=expected
    save('stage.json',info)
    print('MISSING_TEST_PAGE_ASSETS_COPIED_TO_ISOLATED_BUNDLE_ONLY')


def refresh(client,media):
    info=json.loads(MANIFEST.read_text(encoding='utf-8'))
    remote=info['remote']
    if (not remote.startswith('/home/xilinx/gl-hdmi-software-20261008-')
            or '/' in remote.removeprefix('/home/xilinx/')):
        raise ValueError('Unexpected isolated software target')
    if board.audit(client,media)!=json.loads((OUT/'before.json').read_text(encoding='utf-8')):
        raise ValueError('Formal admission changed')
    if (OUT/'board-tests.json').exists():
        save('board-tests-before-refresh.json',json.loads((OUT/'board-tests.json').read_text(encoding='utf-8')))
    with client.open_sftp() as ftp:
        for name,local in local_files().items():
            expected=hashlib.sha256(local.read_bytes()).hexdigest()
            target=remote+'/'+name
            if info['hashes'].get(name)==expected:continue
            ftp.put(str(local),target);ftp.chmod(target,0o600)
            if board.execute(client,shlex.join(['sha256sum',target])).split()[0]!=expected:
                raise ValueError('Software refresh transfer mismatch: '+name)
            info['hashes'][name]=expected
    save('stage.json',info)
    print('ISOLATED_SOFTWARE_BUNDLE_UPDATED_NO_RUNTIME_STARTED',remote)


def check(client,media,focus_native=False):
    info=json.loads(MANIFEST.read_text(encoding='utf-8'));remote=info['remote']
    for name,expected in info['hashes'].items():
        actual=board.execute(client,shlex.join(['sha256sum',remote+'/'+name])).split()[0]
        if actual!=expected:raise ValueError('Software bundle changed: '+name)
    native=remote+'/phone_video_upload/libguardianloop_scan.so'
    result=board.execute(client,shlex.join(['gcc','-std=gnu11','-O3','-mcpu=cortex-a9','-mfpu=neon',
        '-Wall','-Wextra','-Werror','-fPIC','-shared','-pthread',
        remote+'/phone_video_upload/native_scan.c','-o',native]))
    native_hash=board.execute(client,shlex.join(['sha256sum',native])).split()[0]
    save('native-build.json',dict(output=result,exit_code=0,sha256=native_hash,library=native,
        hardware_tested=False,pl_loads=0))
    env=['nice','-n','19','env','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1',
         'PYTHONPATH='+':'.join([remote+'/runtime',remote+'/phone_video_upload',
                               remote+'/wheelchair_ssvep',remote,info['eye_root']+'/src']),
         'GL_TEST_EYE_ROOT='+info['eye_root'],board.PYTHON]
    env.insert(-1,'GL_NATIVE_SCAN_LIBRARY='+native)
    tests=TESTS if not focus_native else ('test_native_scan','test_hdmi_stimulus','test_media_server',
        'test_player_commands','guardianloop_system.test_core',
        'test_ssvep_cue_runtime.RuntimeTests.test_raw_requirement_cannot_be_forged_and_records_linked_trial')
    command=shlex.join(['timeout','--kill-after=10s','330s',*env,
                       '-m','unittest',*tests,'-v'])+' 2>&1'
    _,stdout,stderr=client.exec_command(command,timeout=360)
    result=stdout.read().decode(errors='replace')+stderr.read().decode(errors='replace')
    exit_code=stdout.channel.recv_exit_status()
    save('board-native-focused-tests.json' if focus_native else 'board-tests.json',
         dict(output=result,exit_code=exit_code,tests=tests,full_suite=not focus_native,
              software_only=True,hardware_tested=False))
    print(result)
    after=board.audit(client,media);save('after.json',after)
    if exit_code:raise RuntimeError('Software tests failed; full diagnostics retained')
    compile_code='import py_compile,sys; [py_compile.compile(p,doraise=True) for p in sys.argv[1:]]'
    names=[remote+'/'+name for name in local_files() if name.endswith('.py')]
    board.execute(client,shlex.join(env+['-c',compile_code,*names]))
    save('board-compile.json',dict(python_files=len(names),exit_code=0,hardware_tested=False))
    preflight_env=env[:-1]+['XILINX_XRT=/usr',
        'GL_NATIVE_BOARD_PREFLIGHT='+info['eye_root']+'/libtobii_display.so',env[-1]]
    result=board.execute(client,shlex.join(['timeout','--kill-after=2s','20s',*preflight_env,
        '-m','unittest','test_native_scan.BoardPreflightTests','-v'])+' 2>&1',root=True)
    save('native-preflight.json',dict(output=result,exit_code=0,pl_loads=0,
                                    display_functions_called=False,worker_started=False))
    print(result)
    result=board.execute(client,shlex.join(env+[remote+'/phone_video_upload/benchmark_hdmi_patches.py',
                                              '--eye-root',info['eye_root']]))
    save('board-ram-benchmark.json',json.loads(result))
    print(result)
    after=board.audit(client,media);save('after.json',after)
    before=json.loads((OUT/'before.json').read_text(encoding='utf-8'))
    if after!=before:raise ValueError('Formal service/PL/protected state changed during software checks')
    print('FORMAL_RELEASE_SERVICES_BOOT_AND_PL_UNCHANGED')


def local_check():
    env=dict(os.environ)
    env['PYTHONPATH']=os.pathsep.join(str(path) for path in
        (ROOT/'pynq_guardianloop',ROOT/'eeg_apps_z15',ROOT/'phone_video_upload',
         ROOT/'wheelchair_ssvep',ROOT))
    result=subprocess.run([sys.executable,'-m','unittest',*TESTS,'-q'],
                          capture_output=True,text=True,cwd=ROOT,env=env)
    save('local-tests.json',dict(output=result.stdout+result.stderr,exit_code=result.returncode,
                               software_only=True,hardware_tested=False))
    print(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError('Local tests failed; diagnostics retained')
    node=Path('C:/Program Files/nodejs/node.exe')
    result=subprocess.run([str(node),str(ROOT/'phone_video_upload/test_system_mobile.js')],
                          capture_output=True,text=True,cwd=ROOT)
    save('mobile-tests.json',dict(output=result.stdout+result.stderr,exit_code=result.returncode))
    print(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError('Mobile consent regression failed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('stage','check','complete-assets','refresh','local'))
    parser.add_argument('--run-id',help='Fresh evidence directory; leave earlier verified bundles intact')
    parser.add_argument('--native-focus',action='store_true',help='Focused native/STOP tests; retain full-suite evidence')
    args=parser.parse_args()
    if args.run_id:
        if not args.run_id.replace('-','').isalnum():raise ValueError('Invalid evidence run ID')
        global OUT,MANIFEST
        OUT=ROOT/('phone_video_upload/output/hdmi_candidate_20261008-'+args.run_id)
        MANIFEST=OUT/'stage.json'
    if args.action=='local':local_check();return
    media=json.loads(board.STATE.read_text())
    client=board.upload.trial.connect('192.168.2.99')
    try:
        if args.action=='check':check(client,media,args.native_focus)
        else:{'stage':stage,'complete-assets':complete_assets,'refresh':refresh}[args.action](client,media)
    finally:client.close()


if __name__=='__main__':main()
