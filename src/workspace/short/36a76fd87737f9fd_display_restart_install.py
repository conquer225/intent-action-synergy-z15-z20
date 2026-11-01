"""Install the narrow HDMI acquisition-restart repair before restarting display."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from install_calibration_repair import replace, sha, write_json

LIVE = Path('/home/xilinx/gl-hdmi-live-20261008-ea117349')
EYE = Path('/home/xilinx/brain_eye_coexist_20261005/eye/src/coexist_guard.py')
TARGETS = {EYE, LIVE/'media_player.py', LIVE/'system_runtime/guardianloop_system/live_inputs.py',
           LIVE/'boot-pins.json'}


def validate(stage, installed=False):
    plan=json.loads((stage/'guard-plan.json').read_text())
    if not plan['tests_passed'] or plan['boot']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip():
        raise ValueError('Display repair admission changed')
    if len(plan['files'])!=len(TARGETS) or {Path(row['target']) for row in plan['files']}!=TARGETS:
        raise ValueError('Unexpected display repair targets')
    for row in plan['files']:
        path=Path(row['target'])
        if path.is_symlink() or Path(row['key']).name!=row['key']:
            raise ValueError('Linked target or foreign payload')
        if sha(path)!=row['new_sha' if installed else 'old_sha']:
            raise ValueError('Display repair target changed: '+str(path))
        if sha(stage/'payload'/row['key'])!=row['new_sha']:
            raise ValueError('Display repair payload changed')
    return plan


def install(stage):
    plan=validate(stage)
    pid=subprocess.check_output(['systemctl','show',plan['previous_player_unit'],'-p','MainPID','--value'],text=True).strip()
    if pid!='0':raise ValueError('Do not replace a running display session')
    backup=stage/'backup';backup.mkdir(mode=0o700)
    for row in plan['files']:shutil.copy2(row['target'],backup/row['key'])
    write_json(stage/'guard-installation.json',dict(phase='backed_up',files=plan['files']))
    try:
        for row in plan['files']:replace(stage/'payload'/row['key'],Path(row['target']),row['mode'])
        validate(stage,installed=True)
        for path,digest in json.loads((LIVE/'boot-pins.json').read_text())['files'].items():
            if Path(path).is_symlink() or sha(Path(path))!=digest:
                raise ValueError('Boot pin differs: '+path)
        import sys
        sys.path.insert(0,str(EYE.parent))
        from coexist_guard import CoexistGuard
        from pynq import PL
        report=CoexistGuard(EYE.parent.parent,PL.bitfile_name,allow_acquisition_restart=True).verify()
        write_json(stage/'guard-installation.json',dict(phase='installed',admission=report,files=plan['files']))
        print('DISPLAY_RESTART_REPAIR_INSTALLED_NO_SERVICE_OR_PL_CHANGE',flush=True)
    except BaseException:
        rollback(stage)
        raise


def rollback(stage):
    plan=json.loads((stage/'guard-plan.json').read_text())
    if {Path(row['target']) for row in plan['files']}!=TARGETS:raise ValueError('Foreign repair plan')
    for row in plan['files']:
        if sha(stage/'backup'/row['key'])!=row['old_sha'] or sha(Path(row['target'])) not in (row['old_sha'],row['new_sha']):
            raise ValueError('Refuse to overwrite a later change')
    for row in plan['files']:replace(stage/'backup'/row['key'],Path(row['target']),row['mode'])
    write_json(stage/'guard-installation.json',dict(phase='rolled_back'))
    print('DISPLAY_REPAIR_CHECKSUMMED_ROLLBACK_COMPLETE',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('install','rollback'))
    args=parser.parse_args();stage=Path(__file__).resolve().parent
    if os.geteuid()!=0 or stage.parent!=Path('/home/xilinx') or not stage.name.startswith('gl-display-restart-'):
        raise ValueError('Use the private board-local repair stage')
    globals()[args.action](stage)
