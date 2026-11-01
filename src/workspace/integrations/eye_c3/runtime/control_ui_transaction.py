"""Board-local, private UI update. Never restart acquisition or program PL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

MEDIA=Path('/home/xilinx/gl-media-20261007-314e8796')
FORMAL=Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
ALLOWED={MEDIA/name for name in ('media_server.py','media_player.py','player_commands.py',
    'system_hdmi.py','system_mobile.html','system_mobile.js','menu-shells-portrait-live.npz',
    'test_system_hdmi.py','test_media_server.py','test_player_commands.py')}
ALLOWED|={MEDIA/'system_runtime/guardianloop_system'/name for name in
          ('core.py','live_inputs.py','page_policy.py','test_core.py','test_live_inputs.py')}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def service(name):
    output=subprocess.check_output(['/bin/systemctl','show',name,'-p','MainPID','-p','ActiveState','-p','NRestarts'],text=True)
    return dict(line.split('=',1) for line in output.splitlines())


def replace(source,target,info):
    temporary=target.with_name(target.name+'.control-incoming')
    shutil.copyfile(source,temporary);os.chown(temporary,*info[:2]);os.chmod(temporary,info[2])
    temporary.replace(target)


def idle():
    result=subprocess.run(['pgrep','-f','^'+sys.executable+' '+str(MEDIA/'media_player.py')],capture_output=True,text=True)
    if result.returncode not in (0,1) or result.stdout.strip():raise ValueError('Active/unknown HDMI owner: do not update')
    for suffix in ('-server','-system-server','-control-server'):
        if service(MEDIA.name+suffix)['MainPID']!='0':raise ValueError('Private server must be closed before update')


def rollback(stage):
    idle()
    record=json.loads((stage/'record.json').read_text())
    if record['phase']=='rolled_back':return
    for item in record['files']:
        target=Path(item['target'])
        if target not in ALLOWED or sha(target) not in (item['old_sha'],item['new_sha']):
            raise ValueError('Subsequent modification, refusing rollback: '+str(target))
    for item in record['files']:
        target=Path(item['target'])
        if item['old_sha'] is None:
            if target.exists():target.unlink()  # Only newly added, hash-verified private code.
        else:replace(stage/'backup'/item['key'],target,item['info'])
    record['phase']='rolled_back';(stage/'record.json').write_text(json.dumps(record,indent=2))


def install(stage):
    from pynq import PL
    idle();plan=json.loads((stage/'plan.json').read_text())
    protected={name:service(name) for name in ('guardianloop-cyton','guardianloop-web')}
    if any(row['ActiveState']!='active' for row in protected.values()):raise ValueError('Formal services not ready')
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if boot!=plan['boot_id'] or PL.bitfile_name!=plan['pl']:raise ValueError('Board state changed')
    release=json.loads((FORMAL/'release_manifest.json').read_text())
    if sha(FORMAL/'release_manifest.json')!=plan['manifest_sha']:raise ValueError('Release changed')
    if not all(sha(FORMAL/name)==digest for name,digest in release['files'].items()):raise ValueError('Formal checksum mismatch')
    backup=stage/'backup';backup.mkdir(mode=0o700)
    record=dict(phase='prepared',files=[])
    for item in plan['files']:
        target=Path(item['target']);incoming=stage/'payload'/item['key']
        if target not in ALLOWED or sha(target)!=item['old_sha'] or sha(incoming)!=item['new_sha']:
            raise ValueError('Target or payload changed')
        if target.suffix=='.py':compile(incoming.read_text(),str(target),'exec')
        if target.exists():
            stat=target.stat();info=[stat.st_uid,stat.st_gid,stat.st_mode&0o777]
            shutil.copy2(target,backup/item['key'])
        else:
            stat=target.parent.stat();info=[stat.st_uid,stat.st_gid,0o600]
        record['files'].append(dict(item,info=info))
    (stage/'record.json').write_text(json.dumps(record,indent=2))
    try:
        for item in record['files']:replace(stage/'payload'/item['key'],Path(item['target']),item['info'])
        env=dict(os.environ,PYTHONPATH=str(MEDIA/'system_runtime')+':'+plan['eye_root']+'/src',
                 GL_TEST_EYE_ROOT=plan['eye_root'],XILINX_XRT='/usr')
        subprocess.run([sys.executable,'-m','unittest','guardianloop_system.test_core',
            'guardianloop_system.test_live_inputs','test_media_server','test_player_commands',
            'test_system_hdmi.UnifiedTests.test_already_progressed_latch_does_not_wait_for_an_extra_scan',
            'test_system_hdmi.UnifiedTests.test_frozen_scan_and_bad_latch_rejected',
            'test_system_hdmi.UnifiedTests.test_c_fitter_exact_reference_and_padding_guard','-q'],
            cwd=MEDIA,env=env,check=True,timeout=60)
        sys.path.insert(0,str(MEDIA));sys.path.insert(0,str(MEDIA/'system_runtime'))
        from system_hdmi import UnifiedDisplay
        display=UnifiedDisplay(plan['eye_root'],live=True,dimensions=(288,512),
                               shell_cache=MEDIA/'menu-shells-portrait-live.npz')
        if (protected!={name:service(name) for name in protected} or PL.bitfile_name!=plan['pl']
                or boot!=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
                or sha(FORMAL/'release_manifest.json')!=plan['manifest_sha']):
            raise ValueError('Protected board state changed')
        if not all(sha(Path(i['target']))==i['new_sha'] for i in record['files']):raise ValueError('Installed checksum mismatch')
        result=dict(passed=True,files=len(record['files']),shells=len(display.shells),
            formal_services_unchanged=True,formal_release_unchanged=True,models_unchanged=True,
            boot_unchanged=True,pl_unchanged=True,hdmi_scan_tested=False,human_ssvep_tested=False,
            physical_output_enabled=False,backup=str(backup))
        record['phase']='verified';(stage/'record.json').write_text(json.dumps(record,indent=2))
        (stage/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
    except Exception:
        rollback(stage);raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('install','rollback'))
    args=parser.parse_args();stage=Path(__file__).resolve().parent
    if os.geteuid()!=0 or stage.parent!=Path('/home/xilinx') or not stage.name.startswith('gl-control-ui-'):
        raise ValueError('Only pinned board-local root transaction is allowed')
    globals()[args.action](stage)
