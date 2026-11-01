"""Pinned software update with checksummed backups and independent rollback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
EYE = Path('/home/xilinx/brain_eye_coexist_20261005/eye/src/coexist_guard.py')
STARTUP = Path('/run/guardianloop-startup/status.json')
OVERRIDE = Path('/run/systemd/system/guardianloop-cyton.service.d/90-guardianloop-hdmi-test.conf')
MEDIA = Path('/home/xilinx/gl-media-20261007-314e8796')
FORMAL_NAMES = {'cyton_guardianloop.py','cyton_fatigue.py','calibration_session.py',
    'cyton_sqi.py','seed_replay_check.py','seed_quality_runtime.py',
    'guardianloop_web.py','mobile.js','release_manifest.json'}
FORMAL_NAMES.update({'wear_session.py','ssvep_recording.py','cyton_trial_recorder.py',
                     'ssvep_free.py','ssvep_hdmi.py','ssvep_cue_runtime.py'})
UI_NAMES = {'system_hdmi.py','system_mobile.js','system_runtime/guardianloop_system/live_inputs.py'}
LIVE_NAMES = {'media_server.py','media_player.py','prewear.py','hdmi_stimulus.py',
              'system_mobile.html','hdmi_live_session.py','hdmi_boot.py','boot-pins.json',
              'media_state.json','system_runtime/guardianloop_system/core.py'}
BOOT_UNIT='guardianloop-hdmi-entry.service'
PRIMARY_OVERRIDE = Path('/etc/systemd/system/guardianloop-cyton.service.d/60-primary-worker.conf')
PRIMARY_CONFIG = '[Service]\nEnvironment=GL_PRIMARY_EXECUTION=async\nRuntimeDirectoryPreserve=yes\n'
PRIMARY_NAMES = {'cyton_guardianloop.py', 'cyton_sqi.py', 'guardianloop_acquisition.py',
                 'primary_window.py', 'async_primary.py', 'telemetry_json.py', 'release_manifest.json'}
INPUT_NAMES = {'cyton_guardianloop.py','cyton_sqi.py','cyton_reader_sink.py','mi_acquisition.py','ssvep_acquisition.py',
               'ssvep_cue_runtime.py','page_policy.py','guardianloop_web.py','ssvep_free.html',
               'ssvep_input_prepare.js','release_manifest.json'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def control(*args):
    return subprocess.run(['systemctl',*args],check=True,capture_output=True,text=True,timeout=55).stdout.strip()


def write_json(path, row):
    temporary=path.with_name(path.name+'.repair-new')
    temporary.write_text(json.dumps(row,indent=2));temporary.chmod(0o600);temporary.replace(path)


def replace(source,target,mode):
    temporary=target.with_name(target.name+'.repair-new')
    shutil.copyfile(source,temporary);temporary.chmod(mode);temporary.replace(target)


def allowed(plan):
    live=Path(plan['live'])
    if live.parent!=ROOT.parent.parent or not live.name.startswith('gl-hdmi-live-20261008-'):
        raise ValueError('Foreign HDMI session')
    if (plan.get('page_timing_update') or plan.get('prewear_issue_update')) and plan.get('input_repair_update') is not True:
        raise ValueError('Page timing requires the calibration-preserving input repair')
    if plan.get('report_connection_update') and plan.get('input_repair_update') is not True:
        raise ValueError('Report connection update requires calibration-preserving input repair')
    if plan.get('hdmi_scan_update') and plan.get('report_connection_update') is not True:
        raise ValueError('HDMI scan update requires the pinned report connection update')
    if plan.get('hdmi_worker_schedule_update') is True:
        if (plan.get('input_repair_update') is not True
                or any(plan.get(k) for k in ('primary_worker_update','prewear_update',
                    'page_timing_update','prewear_issue_update','hdmi_report_update',
                    'report_connection_update','hdmi_scan_update'))
                or plan['web_services']!=['guardianloop-web.service',live.name+'-server.service']):
            raise ValueError('Worker schedule requires the narrow calibration-preserving update')
        return {live/'hdmi_live_entry.py',live/'boot-pins.json'}
    if plan.get('hdmi_report_update') is True:
        if any(plan.get(k) for k in ('primary_worker_update','input_repair_update','prewear_update')):
            raise ValueError('HDMI report repair must remain narrow')
        runtime=Path('/home/xilinx/gl-hdmi-software-20261008-6797e092/runtime')
        if plan['web_services']!=[live.name+'-server.service']:
            raise ValueError('Only the existing display web service may restart')
        return {ROOT/'ssvep_hdmi.py',ROOT/'release_manifest.json',EYE,STARTUP,
                runtime/'ssvep_hdmi.py',live/'state.json',live/'boot-pins.json',live/'media_state.json',
                live/'hdmi_stimulus.py',live/'media_player.py',live/'system_hdmi.py',live/'system_mobile.js',
                live/'system_runtime/guardianloop_system/core.py',live/'menu-shells-portrait-live.npz'}
    if plan.get('input_repair_update') is True:
        runtime=Path('/home/xilinx/gl-hdmi-software-20261008-6797e092/runtime')
        if plan.get('primary_worker_update') or plan.get('prewear_update'):
            raise ValueError('Input repair cannot combine installation modes')
        if plan['web_services']!=['guardianloop-web.service',live.name+'-server.service']:
            raise ValueError('Unexpected input-repair web services')
        if plan.get('report_connection_update') is True:
            if plan.get('page_timing_update') or plan.get('prewear_issue_update'):
                raise ValueError('Do not combine narrow connection update modes')
            targets = {ROOT/'ssvep_cue_runtime.py',ROOT/'release_manifest.json',EYE,STARTUP,
                       live/'state.json',live/'boot-pins.json',runtime/'ssvep_cue_runtime.py'}
            if plan.get('hdmi_scan_update') is True:
                targets |= {live/'native_scan.py',live/'hdmi_stimulus.py',
                            live/'libguardianloop_scan.so',live/'media_state.json'}
            return targets
        if plan.get('prewear_issue_update') is True:
            if plan.get('page_timing_update'):
                raise ValueError('Do not combine narrow update modes')
            return {ROOT/n for n in ('guardianloop_web.py','mobile.js','async_primary.py',
                                    'cyton_guardianloop.py','release_manifest.json')}|{
                    EYE,STARTUP,live/'state.json',live/'boot-pins.json'}
        if plan.get('page_timing_update') is True:
            return {ROOT/'page_policy.py',ROOT/'release_manifest.json',EYE,STARTUP,
                    live/'state.json',live/'boot-pins.json',live/'media_player.py'}
        return {ROOT/n for n in INPUT_NAMES}|{EYE,STARTUP,live/'state.json',live/'boot-pins.json',
                                             runtime/'ssvep_cue_runtime.py'}
    if plan.get('primary_worker_update') is True:
        if plan.get('prewear_update') or plan['web_services']:
            raise ValueError('Primary update must not change display or web services')
        return {ROOT/n for n in PRIMARY_NAMES}|{STARTUP,PRIMARY_OVERRIDE,live/'state.json',live/'boot-pins.json'}
    targets={ROOT/n for n in FORMAL_NAMES}|{EYE,STARTUP,OVERRIDE,live/'state.json'}|{
        base/n for base in (MEDIA,live) for n in UI_NAMES}
    if plan.get('prewear_update') is True:
        runtime=Path(plan['candidate_runtime'])
        if runtime.parent.name!='gl-hdmi-software-20261008-6797e092' or runtime.name!='runtime':
            raise ValueError('Foreign candidate runtime')
        targets|={live/n for n in LIVE_NAMES}|{runtime/n for n in ('ssvep_hdmi.py','ssvep_cue_runtime.py')}
        targets.add(Path('/etc/systemd/system')/BOOT_UNIT)
    return targets


def verify_targets(plan,installed=False):
    targets=allowed(plan)
    seen=set()
    for row in plan['files']:
        path=Path(row['target'])
        if (path not in targets or path.is_symlink() or path in seen
                or Path(row['key']).name!=row['key']):raise ValueError('Foreign, duplicate or linked target')
        seen.add(path)
        if plan.get('prewear_issue_update') and path==STARTUP:
            if row.get('new_mode')!=0o644:
                raise ValueError('Public startup status must remain readable by the web service')
            if installed and path.stat().st_mode&0o777!=row['new_mode']:
                raise ValueError('Installed permission differs: '+str(path))
        if sha(path)!=(row['new_sha'] if installed else row['old_sha']):
            raise ValueError('Target changed: '+str(path))
    if (plan.get('primary_worker_update') or plan.get('input_repair_update') or plan.get('hdmi_report_update')) and seen!=targets:
        raise ValueError('Update requires the complete pinned target set')


def verify_running_ui(plan):
    for unit, expected in plan['untouched_services'].items():
        pid=int(control('show',unit,'-p','MainPID','--value') or 0)
        if pid!=expected['pid'] or pid<=0:
            raise ValueError('UI process changed: '+unit)
        fields=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()
        if int(fields[19])!=expected['start_ticks']:
            raise ValueError('UI process identity changed: '+unit)


def rollback(stage):
    record=json.loads((stage/'installation.json').read_text())
    plan=json.loads((stage/'deployment-plan.json').read_text())
    caches=[]
    cache_record=stage/'menu-cache-repair.json'
    if cache_record.exists():
        caches=json.loads(cache_record.read_text())
        expected={str(Path(base)/'menu-shells-portrait-live.npz') for base in (plan['live'],str(MEDIA))}
        if len(caches)!=2 or {row['target'] for row in caches}!=expected:
            raise ValueError('Unexpected menu recovery targets')
        for row in caches:
            backup=Path(row['backup'])
            if backup.parent!=stage or backup.is_symlink() or sha(backup)!=row['old_sha']:
                raise ValueError('Menu recovery checksum differs')
            target=Path(row['target'])
            if target.is_symlink() or sha(target) not in (row['old_sha'],row['new_sha']):
                raise ValueError('Menu rollback refuses a later modification')
    for row in plan['files']:
        target=Path(row['target'])
        if target not in allowed(plan) or sha(target) not in (row['old_sha'],row['new_sha']):
            raise ValueError('Rollback refuses a later modification')
        if row['old_sha'] is not None and sha(stage/'backup'/row['key'])!=row['old_sha']:
            raise ValueError('Recovery backup checksum differs')
    if plan.get('prewear_update') is True and record.get('boot_entry_enabled'):
        control('disable',BOOT_UNIT)
    control('stop','guardianloop-cyton.service')
    for row in plan['files']:
        target=Path(row['target'])
        if row['old_sha'] is None:
            if target.exists():target.unlink()
        else:replace(stage/'backup'/row['key'],target,row['old_mode'])
    for row in caches:
        replace(Path(row['backup']),Path(row['target']),0o644)
    control('daemon-reload')
    control('start','guardianloop-cyton.service')
    for unit in plan['web_services']:control('restart',unit)
    record['phase']='rolled_back';write_json(stage/'installation.json',record)
    print('CHECKSUMMED_SOFTWARE_ROLLBACK_COMPLETE',flush=True)


def install(stage):
    plan=json.loads((stage/'deployment-plan.json').read_text())
    if (not plan['tests_passed'] or sha(ROOT/'release_manifest.json')!=plan['previous_manifest_sha']
            or Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=plan['boot']):
        raise ValueError('Admission state changed')
    primary=plan.get('primary_worker_update') is True
    if primary:
        verify_running_ui(plan)
    elif int(control('show',plan['display_unit'],'-p','MainPID','--value') or 0):
        raise ValueError('Display must finish recovery before updating acquisition')
    manifest=json.loads((ROOT/'release_manifest.json').read_text())
    for name,digest in manifest['files'].items():
        if Path(name).name!=name or sha(ROOT/name)!=digest:raise ValueError('Formal release differs')
    verify_targets(plan)
    backup=stage/'backup';backup.mkdir(mode=0o700)
    for row in plan['files']:
        if sha(stage/'payload'/row['key'])!=row['new_sha']:raise ValueError('Payload checksum differs')
        if row['old_sha'] is not None:shutil.copy2(row['target'],backup/row['key'])
    if plan.get('input_repair_update') or plan.get('hdmi_report_update'):
        if control('show','guardianloop-cyton.service','-p','RuntimeDirectoryPreserve','--value')!='yes':
            raise ValueError('Calibration directory preservation is required')
    if primary:
        override=next(row for row in plan['files'] if Path(row['target'])==PRIMARY_OVERRIDE)
        if (stage/'payload'/override['key']).read_text()!=PRIMARY_CONFIG:
            raise ValueError('Unexpected primary service configuration')
    if primary or plan.get('input_repair_update') or plan.get('hdmi_report_update'):
        release=backup/'release';release.mkdir(mode=0o700)
        for name in (*manifest['files'],'release_manifest.json'):
            shutil.copy2(ROOT/name,release/name)
        calibration=backup/'calibration';calibration.mkdir(mode=0o700)
        for name in ('calibration-session.json','wear-session.json'):
            path=Path('/run/guardianloop')/name
            if path.exists():shutil.copy2(path,calibration/name)
    record=dict(phase='prepared',rollback_unit=stage.name+'-rollback')
    write_json(stage/'installation.json',record)
    rollback_after='240s' if plan.get('report_connection_update') is True else '150s'
    subprocess.run(['systemd-run','--unit='+record['rollback_unit'],'--on-active='+rollback_after,
        '--timer-property=AccuracySec=1s',sys.executable,str(Path(__file__).resolve()),'rollback'],
        check=True,capture_output=True,text=True,timeout=15)
    try:
        if primary:
            # Preserve the current boot's calibration before stopping its owner.
            replace(stage/'payload'/override['key'],PRIMARY_OVERRIDE,override['new_mode'])
            control('daemon-reload')
            if control('show','guardianloop-cyton.service','-p','RuntimeDirectoryPreserve','--value')!='yes':
                raise ValueError('Calibration directory preservation was not applied')
        control('stop','guardianloop-cyton.service')
        for row in plan['files']:replace(stage/'payload'/row['key'],Path(row['target']),row['new_mode'])
        verify_targets(plan,installed=True)
        sys.path.insert(0,str(ROOT))
        from guardianloop_startup import verify_files
        verify_files(ROOT,json.loads((ROOT/'release_manifest.json').read_text()))
        control('daemon-reload');control('start','guardianloop-cyton.service')
        for unit in plan['web_services']:control('restart',unit)
        if primary:verify_running_ui(plan)
        record['phase']='awaiting_live_check';write_json(stage/'installation.json',record)
        print(json.dumps(record),flush=True)
    except BaseException:
        rollback(stage);control('stop',record['rollback_unit']+'.timer');raise


def commit(stage):
    plan=json.loads((stage/'deployment-plan.json').read_text());verify_targets(plan,installed=True)
    for unit in ('guardianloop-cyton.service',*plan['web_services']):control('is-active',unit)
    if plan.get('primary_worker_update') is True:verify_running_ui(plan)
    record=json.loads((stage/'installation.json').read_text())
    if record['phase']!='awaiting_live_check':raise ValueError('Not awaiting a live check')
    control('stop',record['rollback_unit']+'.timer')
    if plan.get('prewear_update') is True:
        control('enable',BOOT_UNIT)
        record['boot_entry_enabled']=True
    record['phase']='committed';write_json(stage/'installation.json',record)
    print('CALIBRATION_REPAIR_COMMITTED_BACKUP_RETAINED',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('install','rollback','commit'))
    args=parser.parse_args();stage=Path(__file__).resolve().parent
    if os.geteuid()!=0 or stage.parent!=Path('/home/xilinx') or not stage.name.startswith('gl-calibration-install-'):
        raise ValueError('Run only the staged board-local installer as root')
    globals()[args.action](stage)
