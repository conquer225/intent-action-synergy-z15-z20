"""Stage only private media candidates; hardware actions are explicit separate commands."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import uuid
import secrets

import stage_server as upload

ROOT=Path(__file__).resolve().parent
STATE=ROOT/'media_state.json'
PYTHON='/usr/local/share/pynq-venv/bin/python3'


def stage(c):
    if STATE.exists():raise ValueError('Retained media stage must be inspected')
    previous=json.loads((ROOT/'playback_state.json').read_text())
    remote='/home/xilinx/gl-media-20261007-'+uuid.uuid4().hex[:8]
    state={'remote':remote,'prefix':remote.rsplit('/',1)[-1],
        'source':previous['remote']+'/video_1280x720.mp4',
        'uploaded_root':json.loads(upload.STATE.read_text())['remote']+'/uploads',
        'original_overlay':previous['original_overlay'],'display_overlay':previous['display_overlay'],
        'eye_root':'/home/xilinx/brain_eye_coexist_20261005/eye',
        'before_services':upload.trial.services(c),'before_hashes':upload.trial.protected(c)}
    upload.trial.execute(c,'mkdir -m 700 '+shlex.quote(remote))
    STATE.write_text(json.dumps(state,indent=2))
    update(c,state)
    flags=' -O3 -mcpu=cortex-a9 -mfpu=neon -Wall -Wextra -Werror -I/usr/include/arm-linux-gnueabihf '
    for source,binary,extra in [('frame_decoder.c','frame_decoder.so',' -fPIC -shared '),
                                ('audio_probe.c','audio_probe',' '),('transcode_video.c','transcode_video',' ')]:
        upload.trial.execute(c,'gcc'+flags+extra+shlex.quote(remote+'/'+source)+' -o '+
            shlex.quote(remote+'/'+binary)+' -lavformat -lavcodec -lavutil -lswscale -lm')
    upload.trial.execute(c,'cp -n -- /home/xilinx/tobii_z15/libtobii_display.so '+shlex.quote(remote+'/libtobii_display.so'))
    cmd='systemd-run --unit='+state['prefix']+'-prepare --uid=xilinx --property=RuntimeMaxSec=15min '+\
        '--property=TimeoutStopSec=5s --property=MemoryMax=256M --property=Nice=8 --property=LimitCORE=0 '+\
        PYTHON+' '+shlex.quote(remote+'/prepare_chunks.py')+' --source '+shlex.quote(state['source'])+\
        ' --output '+shlex.quote(remote+'/fixture60')+' --repeat-fixture 22'
    print(upload.trial.execute(c,cmd,root=True))
    print('PRIVATE_CACHE_PREPARATION_STARTED',remote,flush=True)


def update(c,state):
    remote=state['remote']
    with c.open_sftp() as sftp:
        for path in ROOT.glob('*'):
            if path.suffix not in ('.py','.c','.html','.js'):continue
            sftp.put(str(path),remote+'/'+path.name)
            sftp.chmod(remote+'/'+path.name,0o600)
            actual=upload.trial.execute(c,'sha256sum '+shlex.quote(remote+'/'+path.name)).split()[0]
            if actual!=hashlib.sha256(path.read_bytes()).hexdigest():raise ValueError('Source transfer mismatch')
        with sftp.open(remote+'/media_state.json','w') as handle:handle.write(json.dumps(state))
        sftp.chmod(remote+'/media_state.json',0o600)


def server(c,state):
    remote=state['remote']
    before=json.loads(upload.trial.execute(c,'cat /home/xilinx/jupyter_notebooks/guardianloop_pynq/release_manifest.json'))
    state['release_id']=before['release_id']
    paths=[state['original_overlay'],state['original_overlay'].rsplit('.',1)[0]+'.hwh',
           state['display_overlay'],state['display_overlay'].rsplit('.',1)[0]+'.hwh']
    state['hardware_hashes']={path:upload.trial.execute(c,'sha256sum '+shlex.quote(path)).split()[0] for path in paths}
    if state['hardware_hashes'][state['display_overlay']]!='8b52892466a1b4d025c5c693a951727ae6215e57ca3e5fa0dedaa2a1d510d50f':
        raise ValueError('Unrecognized display PL')
    state['key']=state.get('key') or secrets.token_hex(16)
    with c.open_sftp() as sftp:
        with sftp.open(remote+'/access.key','w') as handle:handle.write(state['key'])
        sftp.chmod(remote+'/access.key',0o600)
    STATE.write_text(json.dumps(state,indent=2));update(c,state)
    upload.trial.execute(c,'gcc -O3 -mcpu=cortex-a9 -mfpu=neon -Wall -Wextra -Werror '+
        shlex.quote(remote+'/transcode_video.c')+' -o '+shlex.quote(remote+'/transcode_video')+
        ' -lavformat -lavcodec -lavutil -lswscale')
    unit=state['prefix']+'-server'
    print(upload.trial.execute(c,'systemd-run --unit='+unit+' --property=RuntimeMaxSec=35min '+
        '--property=TimeoutStopSec=10s --property=MemoryMax=384M --property=LimitCORE=0 '+
        'env XILINX_XRT=/usr '+PYTHON+' '+shlex.quote(remote+'/media_server.py')+
        ' --key-file '+shlex.quote(remote+'/access.key'),root=True))
    print('PHONE_ENTRY_STARTED (access code retained privately)')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('stage','status','update','bench','audio','server'))
    args=p.parse_args();c=upload.trial.connect('192.168.2.99')
    try:
        if args.action=='stage':stage(c)
        else:
            state=json.loads(STATE.read_text());remote=state['remote']
            if args.action=='update':update(c,state)
            elif args.action=='server':server(c,state)
            elif args.action=='status':print(upload.trial.execute(c,'systemctl show '+state['prefix']+'-prepare -p ActiveState -p MainPID -p Result -p ExecMainStatus; journalctl -u '+state['prefix']+'-prepare --no-pager -n 3'))
            elif args.action=='bench':
                update(c,state)
                print(upload.trial.execute(c,'systemd-run --unit='+state['prefix']+'-bench '+
                    '--uid=xilinx --property=RuntimeMaxSec=300s --property=MemoryMax=256M '+PYTHON+' '+
                    shlex.quote(remote+'/bench_chunks.py')+' --cache '+shlex.quote(remote+'/fixture60')+
                    ' --unpaced --output '+shlex.quote(remote+'/bench_report.json'),root=True))
            else:print(upload.trial.execute(c,shlex.quote(remote+'/audio_probe')+' '+shlex.quote(state['uploaded_root']+'/d87609d9be1c4738ba9dc378438d9935.mp4')))
    finally:c.close()
