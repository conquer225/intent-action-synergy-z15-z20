"""Private integration deployment; no formal edits or permanent boot installation."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import sys

import stage_server as upload
from stage_media import STATE,PYTHON,update

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'phone_video_upload/output/live_system_20261007'


def execute(c,cmd,root=False):return upload.trial.execute(c,cmd,root=root)


def audit(c,s):
    manifest=json.loads(execute(c,'cat /home/xilinx/jupyter_notebooks/guardianloop_pynq/release_manifest.json'))
    hashes=execute(c,'sha256sum '+' '.join(shlex.quote('/home/xilinx/jupyter_notebooks/guardianloop_pynq/'+n) for n in manifest['files']),True)
    return dict(release_unchanged={line.split()[1].rsplit('/',1)[-1]:line.split()[0] for line in hashes.splitlines()}==manifest['files'],
        services=upload.trial.services(c),protected=upload.trial.protected(c),
        boot=execute(c,'cat /proc/sys/kernel/random/boot_id').strip(),
        pl=execute(c,'env XILINX_XRT=/usr '+PYTHON+' -c '+shlex.quote('from pynq import PL; print(PL.bitfile_name)'),True).strip())


def stage(c,s):
    if execute(c,'pgrep -f '+shlex.quote('^'+PYTHON+' '+s['remote']+'/media_player.py')+' || true').strip():
        raise ValueError('Do not update private code while display runs')
    OUT.mkdir(parents=True,exist_ok=True);before=audit(c,s)
    (OUT/'before.json').write_text(json.dumps(before,indent=2))
    if not before['release_unchanged'] or before['pl']!=s['original_overlay']:raise ValueError('Admission state changed')
    update(c,s)
    with c.open_sftp() as ftp:
        for name in ('__init__.py','core.py','live_inputs.py','eye_entry.py','media_library.py','page_policy.py','test_core.py','test_live_inputs.py','test_eye_entry.py'):
            local=ROOT/'guardianloop_system'/name;target=s['remote']+'/system_runtime/guardianloop_system/'+name
            ftp.put(str(local),target);ftp.chmod(target,0o600)
            if execute(c,'sha256sum '+shlex.quote(target)).split()[0]!=hashlib.sha256(local.read_bytes()).hexdigest():
                raise ValueError('Transferred source differs')
    for name in ('frame_decoder','transcode_video'):
        shared=' -fPIC -shared' if name=='frame_decoder' else ''
        print(execute(c,'gcc -O3 -mcpu=cortex-a9 -mfpu=neon -Wall -Wextra -Werror'+shared+' '+
            s['remote']+'/'+name+'.c -o '+s['remote']+'/'+name+('.so' if shared else '')+
            ' -lavformat -lavcodec -lavutil -lswscale -lm'))
    print(execute(c,'cd '+s['remote']+' && env PYTHONPATH='+s['remote']+'/system_runtime:'+s['eye_root']+'/src '+
        PYTHON+' -m unittest test_portrait -v'))
    print('PRIVATE_LIVE_SOURCES_STAGED')


def server(c,s):
    print(execute(c,shlex.join(['systemd-run','--unit='+s['prefix']+'-system-server',
        '--property=RuntimeMaxSec=40min','--property=TimeoutStopSec=10s','--property=MemoryMax=384M',
        '--property=LimitCORE=0','env','XILINX_XRT=/usr',PYTHON,s['remote']+'/media_server.py',
        '--key-file',s['remote']+'/access.key']),True))
    print('PRIVATE_MOBILE_ENTRY_STARTED')


def status(c,s):
    print(execute(c,'systemctl show '+s['prefix']+'-system-server -p MainPID -p ActiveState -p Result'))
    for path in (s['remote']+'/player_status.json','/dev/shm/'+s['prefix']+'-player-status.json'):
        print(execute(c,'test ! -f '+path+' || cat '+path))


def collect(c,s):
    OUT.mkdir(parents=True,exist_ok=True)
    with c.open_sftp() as ftp:
        for name in ftp.listdir(s['remote']):
            if name.startswith('play-') and not name.startswith('play-system-') and name.endswith('-report.json'):
                raw=execute(c,'cat '+shlex.quote(s['remote']+'/'+name),True)
                (OUT/name).write_text(json.dumps(json.loads(raw),indent=2),encoding='utf-8')
        for name in ('ratings.json','player_status.json'):
            try:ftp.stat(s['remote']+'/'+name)
            except FileNotFoundError:continue
            raw=execute(c,'cat '+shlex.quote(s['remote']+'/'+name),True)
            (OUT/name).write_text(json.dumps(json.loads(raw),indent=2),encoding='utf-8')
    after=audit(c,s);before=json.loads((OUT/'before.json').read_text())
    after.update(protected_unchanged=after['protected']==before['protected'],
        services_unchanged=after['services']==before['services'],boot_unchanged=after['boot']==before['boot'],
        original_pl_restored=after['pl']==s['original_overlay'],audio_output=False,physical_output_enabled=False)
    (OUT/'after.json').write_text(json.dumps(after,indent=2))
    print(json.dumps({k:v for k,v in after.items() if k not in ('protected','services')}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('stage','server','status','collect'));args=p.parse_args()
    s=json.loads(STATE.read_text());c=upload.trial.connect('192.168.2.99')
    try:globals()[args.action](c,s)
    finally:c.close()
