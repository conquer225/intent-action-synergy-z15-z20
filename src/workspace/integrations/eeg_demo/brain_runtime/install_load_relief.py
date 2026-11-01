"""Install a pinned software-only package, with an independent rollback timer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
MEDIA=Path('/home/xilinx/gl-media-20261007-314e8796')
EYE=Path('/home/xilinx/brain_eye_coexist_20261005/eye/src/coexist_guard.py')
OVERRIDE=Path('/etc/systemd/system/guardianloop-cyton.service.d/50-load-relief.conf')
STARTUP=Path('/run/guardianloop-startup/status.json')
ALLOWED={ROOT/name for name in ('cyton_guardianloop.py','cyton_covariance.py','ssvep_acquisition.py',
    'async_seed_candidate.py','page_policy.py','release_manifest.json')}
ALLOWED|={MEDIA/name for name in ('system_hdmi.py','media_player.py','menu-shells-portrait-live.npz',
    'system_runtime/guardianloop_system/page_policy.py')}
ALLOWED|={EYE,OVERRIDE,STARTUP}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def control(*args):
    return subprocess.run(['/bin/systemctl',*args],check=True,timeout=30,capture_output=True,text=True)


def replace(source,target):
    incoming=target.with_name(target.name+'.relief-new')
    shutil.copyfile(source,incoming);os.chmod(incoming,0o644);incoming.replace(target)


def rollback(stage):
    backup=stage/'backup';record=json.loads((backup/'installation.json').read_text())
    # Do not overwrite another person's subsequent modifications.
    for item in record['files']:
        target=Path(item['target'])
        if target not in ALLOWED:raise ValueError('Foreign rollback target')
        if target.exists() and sha(target) not in (item['new_sha'],item['old_sha']):
            raise ValueError('Installed target changed after deployment: '+str(target))
    control('stop','guardianloop-cyton')
    try:
        for item in record['files']:
            target=Path(item['target'])
            if item['old_sha'] is None:
                if target.exists():target.unlink()
            else:replace(backup/item['key'],target)
        control('daemon-reload')
    finally:control('start','guardianloop-cyton')
    record['phase']='rolled_back';(backup/'installation.json').write_text(json.dumps(record,indent=2))
    print('SOFTWARE_ROLLBACK_COMPLETE',flush=True)


def install(stage):
    plan=json.loads((stage/'deployment-plan.json').read_text())
    if not plan['gate']['promotion_gate']:raise ValueError('Recorded candidate has not passed')
    if sha(ROOT/'release_manifest.json')!=plan['previous_manifest_sha']:
        raise ValueError('Formal release changed before deployment')
    manifest=json.loads((ROOT/'release_manifest.json').read_text())
    for name,digest in manifest['files'].items():
        if Path(name).name!=name or sha(ROOT/name)!=digest:raise ValueError('Formal checksum changed')
    control('is-active','guardianloop-cyton')
    player=subprocess.run(['pgrep','-f','^'+sys.executable+' '+str(MEDIA/'media_player.py')],
                          capture_output=True,text=True,check=False)
    if player.stdout.strip():raise ValueError('HDMI session must be closed before software update')
    backup=stage/'backup';backup.mkdir(mode=0o700)
    record={'phase':'prepared','files':[],'timer':stage.name+'-rollback'}
    for item in plan['files']:
        target=Path(item['target']);source=stage/'payload'/item['key']
        if target not in ALLOWED or sha(source)!=item['new_sha']:
            raise ValueError('Unverified deployment target or source')
        old=sha(target) if target.exists() else None
        if old!=item['old_sha']:raise ValueError('Target changed since staging: '+str(target))
        if old is not None:shutil.copy2(target,backup/item['key'])
        record['files'].append(item)
    shutil.copy2(STARTUP,backup/'startup-status.json')
    (backup/'installation.json').write_text(json.dumps(record,indent=2))
    subprocess.run(['systemd-run','--unit='+record['timer'],'--on-active=120s',
        '--timer-property=AccuracySec=1s',sys.executable,str(Path(__file__).resolve()),'rollback'],
        check=True,timeout=10,capture_output=True,text=True)
    control('stop','guardianloop-cyton')
    try:
        for item in record['files']:replace(stage/'payload'/item['key'],Path(item['target']))
        # Remove only the old, explicitly closed display-session marker.
        page=Path('/dev/shm/gl-media-20261007-314e8796-system-page.json')
        if page.exists():
            lease=json.loads(page.read_text())
            if lease.get('reason')!='display_session_closed' or lease.get('updated_monotonic')!=0:
                raise ValueError('Unexpected active/stale page owner')
            shutil.copy2(page,backup/'closed-page.json');page.unlink()
        sys.path.insert(0,str(ROOT))
        from guardianloop_startup import verify_files,verify_models,boot_id
        current=json.loads((ROOT/'release_manifest.json').read_text())
        previous=json.loads(STARTUP.read_text())
        if previous['boot_id']!=boot_id() or previous['state']!='ready':
            raise ValueError('Startup contract changed')
        verified=verify_files(ROOT,current)
        with tempfile.TemporaryDirectory(prefix='relief-model-check-',dir=stage) as scratch:
            tasks=verify_models(ROOT,Path(scratch))
        tasks['seed_candidate']['schedule']='paused_optional_diagnostic'
        tasks['ssvep_candidate']['schedule']='HDMI_direction_page_or_standalone'
        previous.update(release_id=current['release_id'],verified_files=verified,tasks=tasks,
                        software_update_without_pl_reload=True)
        incoming=stage/'payload/startup-status.json'
        incoming.write_text(json.dumps(previous,indent=2))
        record['files'].append(dict(key='startup-status.json',target=str(STARTUP),
            old_sha=sha(STARTUP),new_sha=sha(incoming)))
        (backup/'installation.json').write_text(json.dumps(record,indent=2))
        replace(incoming,STARTUP)
        control('daemon-reload');control('start','guardianloop-cyton')
        record['phase']='awaiting_live_check';(backup/'installation.json').write_text(json.dumps(record,indent=2))
    except BaseException:
        rollback(stage);control('stop',record['timer']+'.timer');raise
    print(json.dumps(dict(phase=record['phase'],backup=str(backup),rollback_timer=record['timer'])),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('install','rollback'))
    args=parser.parse_args();stage=Path(__file__).resolve().parent
    if os.geteuid()!=0 or stage.parent!=Path('/home/xilinx') or not stage.name.startswith('gl-load-relief-install-'):
        raise ValueError('Run only the staged board-local installer as root')
    globals()[args.action](stage)
