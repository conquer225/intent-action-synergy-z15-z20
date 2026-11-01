"""Private user-space video fit checks; leave the persistent display owner alone."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shlex

import run_hdmi_live as live

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/video_path_relief_20261009'
DISPLAY='/home/xilinx/gl-hdmi-live-20261008-ea117349'


def save(name,value):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def audit(client):
    command=['systemctl','show','guardianloop-cyton.service','guardianloop-web.service',
             'play-d418a3ca.service','-p','Id','-p','MainPID','-p','NRestarts','-p','ActiveState']
    services=live.board.execute(client,shlex.join(command),root=True)
    snapshot=live.request(client)
    player=snapshot.get('player') or {};system=player.get('system') or {}
    code=('import json,hashlib,sys; from pathlib import Path; p=Path(sys.argv[1]); '
          's=json.loads((p/"media_state.json").read_text()); '
          'print(json.dumps(dict(eye_root=s["eye_root"],hashes={n:hashlib.sha256((p/n).read_bytes()).hexdigest() '
          'for n in ("media_player.py","system_hdmi.py","frame_fitter.so")})))')
    files=json.loads(live.board.execute(client,shlex.join([live.board.PYTHON,'-c',code,DISPLAY]),root=True))
    return dict(services=services,boot=live.board.execute(client,
        'cat /proc/sys/kernel/random/boot_id').strip(),display=DISPLAY,eye_root=files['eye_root'],
        display_hashes=files['hashes'],player_state=player.get('state'),page=system.get('page'),
        frame=player.get('frame'),stimulus=system.get('stimulus_enabled'),
        physical=system.get('physical_output_enabled'))


def stage(client):
    if (OUT/'stage.json').exists():raise ValueError('Inspect and reuse the retained private stage')
    before=audit(client)
    if before['stimulus'] is not False or before['physical'] is not False:
        raise ValueError('No software diagnostic during stimulus or physical control')
    remote=live.board.execute(client,'mktemp -d /home/xilinx/gl-video-path-20261009-XXXXXX').strip()
    if Path(remote).parent!=Path('/home/xilinx') or not Path(remote).name.startswith('gl-video-path-20261009-'):
        raise ValueError('Private directory escaped the intended parent')
    save('stage.json',dict(remote=remote,before=before))
    live.board.execute(client,shlex.join(['cp','--',DISPLAY+'/frame_fitter.so',remote+'/reference.so']),root=True)
    live.board.execute(client,shlex.join(['chown','xilinx:xilinx',remote+'/reference.so']),root=True)
    with client.open_sftp() as ftp:
        hashes={}
        for name in ('frame_fitter.c','benchmark_video_fitter.py'):
            raw=(ROOT/name).read_bytes();ftp.put(str(ROOT/name),remote+'/'+name)
            hashes[name]=hashlib.sha256(raw).hexdigest()
            if hashlib.sha256(ftp.open(remote+'/'+name).read()).hexdigest()!=hashes[name]:
                raise RuntimeError('Private source transfer changed')
        if hashlib.sha256(ftp.open(remote+'/reference.so').read()).hexdigest()!=before['display_hashes']['frame_fitter.so']:
            raise RuntimeError('Reference library copy changed')
    save('candidate-hashes.json',hashes)
    command=['gcc','-O3','-mcpu=cortex-a9','-Wall','-Wextra','-Werror','-fPIC','-shared',
             remote+'/frame_fitter.c','-o',remote+'/candidate.so']
    print(live.board.execute(client,shlex.join(command)))
    print(json.dumps(dict(remote=remote,compiled=True,display_owner_unchanged=True)))


def benchmark(client):
    state=json.loads((OUT/'stage.json').read_text(encoding='utf-8'));remote=state['remote']
    command=['env','OPENBLAS_NUM_THREADS=1',live.board.PYTHON,remote+'/benchmark_video_fitter.py',
             '--reference',remote+'/reference.so','--candidate',remote+'/candidate.so']
    raw=live.board.execute(client,shlex.join(command))
    result=json.loads(raw);save('fitter-benchmark.json',result)
    after=audit(client);save('after.json',after)
    unchanged=all(after[key]==state['before'][key] for key in ('services','boot','display_hashes'))
    if not unchanged:raise RuntimeError('Production or display owner changed during the private check')
    print(json.dumps(dict(result=result,protected_state_unchanged=unchanged)))


def checks(client):
    state=json.loads((OUT/'stage.json').read_text(encoding='utf-8'));remote=state['remote']
    hashes=json.loads((OUT/'candidate-hashes.json').read_text(encoding='utf-8'))
    with client.open_sftp() as ftp:
        for name in ('system_hdmi.py','media_player.py','test_system_hdmi.py','playback_policy.py','benchmark_video_fitter.py'):
            ftp.put(str(ROOT/name),remote+'/'+name)
            hashes[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
            if hashlib.sha256(ftp.open(remote+'/'+name).read()).hexdigest()!=hashes[name]:
                raise RuntimeError('Private display source transfer changed')
    live.board.execute(client,shlex.join(['cp','--',remote+'/candidate.so',remote+'/frame_fitter.so']))
    env=['env','XILINX_XRT=/usr','OPENBLAS_NUM_THREADS=1',
         'PYTHONPATH='+remote+':'+DISPLAY+'/system_runtime:'+state['before']['eye_root']+'/src',live.board.PYTHON]
    names=['test_already_progressed_latch_does_not_wait_for_an_extra_scan',
           'test_frozen_scan_and_bad_latch_rejected',
           'test_prepared_video_waits_only_remaining_time_and_rechecks_guard',
           'test_late_prepared_video_never_waits_or_skips_latch_checks',
           'test_guard_revoked_during_deadline_wait_prevents_submission',
           'test_prepared_video_still_checks_dma_after_successful_latch',
           'test_c_fitter_exact_reference_and_padding_guard']
    command=env+['-m','unittest','-v',*['test_system_hdmi.UnifiedTests.'+n for n in names]]
    log=live.board.execute(client,shlex.join(command)+' 2>&1',root=True)
    save('board-software-tests.json',dict(output=log,hardware_used=False))
    print(log)
    code=('import sys; from system_hdmi import UnifiedDisplay; '
          'u=UnifiedDisplay(sys.argv[1],live=True,dimensions=(288,512)); '
          'u.save_shell_cache(sys.argv[2]); '
          'v=UnifiedDisplay(sys.argv[1],live=True,dimensions=(288,512),shell_cache=sys.argv[2]); '
          'import numpy as np; assert all(np.array_equal(u.shells[k],v.shells[k]) for k in u.shells); '
          'print("PRIVATE_MENU_CACHE_EXACT_NO_HARDWARE")')
    cache_log=live.board.execute(client,shlex.join(env+['-c',code,state['before']['eye_root'],
        remote+'/menu-shells-portrait-live.npz']),root=True)
    print(cache_log)
    code=('import hashlib,json,sys; from pathlib import Path; p=Path(sys.argv[1]); '
          'print(json.dumps({n:hashlib.sha256((p/n).read_bytes()).hexdigest() '
          'for n in ("frame_fitter.so","menu-shells-portrait-live.npz")}))')
    hashes.update(json.loads(live.board.execute(client,shlex.join(env+['-c',code,remote]),root=True)))
    save('candidate-hashes.json',hashes)
    after=audit(client);save('after-checks.json',after)
    if any(after[key]!=state['before'][key] for key in ('services','boot','display_hashes')):
        raise RuntimeError('Production or display owner changed during private checks')


def compare(client):
    state=json.loads((OUT/'stage.json').read_text(encoding='utf-8'))
    differences={}
    for name in ('media_player.py','system_hdmi.py'):
        source=live.board.execute(client,shlex.join(['cat',DISPLAY+'/'+name]),root=True)
        differences[name]='\n'.join(difflib.unified_diff(source.splitlines(),
            (ROOT/name).read_text(encoding='utf-8').splitlines(),fromfile='active/'+name,tofile='candidate/'+name,lineterm=''))
    save('source-differences.json',differences)
    for value in differences.values():print(value)
    after=audit(client)
    if after['display_hashes']!=state['before']['display_hashes']:
        raise RuntimeError('Active display sources changed since staging')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('audit','stage','benchmark','checks','compare'))
    args=parser.parse_args();client=live.board.upload.trial.connect('192.168.2.99')
    try:
        if args.action=='audit':print(json.dumps(audit(client),ensure_ascii=False))
        else:globals()[args.action](client)
    finally:client.close()


if __name__=='__main__':main()
