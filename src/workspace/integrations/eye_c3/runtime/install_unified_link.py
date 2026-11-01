"""Scoped web/bench-link installation; never stops acquisition or HDMI."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


BASE = Path('/home/xilinx/gl-hdmi-live-20261008-ea117349')
TARGETS = {BASE/name for name in ('media_server.py', 'system_mobile.js', 'system_mobile.html',
    'wheelchair_link.py', 'media_state.json', 'boot-pins.json')}
TARGETS.add(BASE/'system_runtime/wheelchair_ssvep/bench_network_bridge.py')


def validate(stage, plan, installed=False):
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != plan['boot']:
        raise ValueError('Board rebooted')
    if {Path(r['target']) for r in plan['files']} != TARGETS or len(plan['files']) != len(TARGETS):
        raise ValueError('Installation scope differs')
    for row in plan['files']:
        target = Path(row['target'])
        if target.is_symlink() or sha(target) != row['new_sha' if installed else 'old_sha']:
            raise ValueError('Target changed: '+str(target))
        if Path(row['key']).name != row['key'] or sha(stage/'payload'/row['key']) != row['new_sha']:
            raise ValueError('Payload changed')
    for name, expected in plan['protected'].items():
        if sha(Path(name)) != expected:
            raise ValueError('Protected artifact changed: '+name)
    for unit, identity in plan['untouched_services'].items():
        pid = int(control('show', unit, '-p', 'MainPID', '--value'))
        if pid != identity['pid']:
            raise ValueError('Protected process restarted: '+unit)
        fields = Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()
        if int(fields[19]) != identity['start_ticks']:
            raise ValueError('Protected process identity changed')


def rollback(stage, plan):
    for row in plan['files']:
        target = Path(row['target'])
        if target not in TARGETS or sha(target) not in (row['new_sha'], row['old_sha']):
            raise ValueError('Rollback refuses later modifications')
        if row['old_sha'] is not None and sha(stage/'backup'/row['key']) != row['old_sha']:
            raise ValueError('Backup differs')
    for row in plan['files']:
        target = Path(row['target'])
        if row['old_sha'] is None:
            target.unlink(missing_ok=True)
        else:
            replace(stage/'backup'/row['key'], target, row['old_mode'])
    control('restart', BASE.name+'-server.service')
    write_json(stage/'installation.json', dict(phase='rolled_back'))


def install(stage, plan):
    if plan['tests_passed'] is not True:
        raise ValueError('Tests did not pass')
    validate(stage, plan)
    backup = stage/'backup';backup.mkdir(mode=0o700)
    for row in plan['files']:
        if row['old_sha'] is not None:
            shutil.copy2(row['target'], backup/row['key'])
    timer = stage.name+'-rollback'
    write_json(stage/'installation.json', dict(phase='prepared', rollback_unit=timer))
    subprocess.run(['systemd-run', '--unit='+timer, '--on-active=180s',
        '--timer-property=AccuracySec=1s', sys.executable, str(Path(__file__).resolve()), 'rollback'],
        check=True, capture_output=True, timeout=15)
    try:
        for row in plan['files']:
            replace(stage/'payload'/row['key'], Path(row['target']), row['new_mode'])
        validate(stage, plan, installed=True)
        control('restart', BASE.name+'-server.service')
        write_json(stage/'installation.json', dict(phase='awaiting_live_check', rollback_unit=timer))
    except BaseException:
        rollback(stage, plan)
        control('stop', timer+'.timer')
        raise


def commit(stage, plan):
    validate(stage, plan, installed=True)
    record = json.loads((stage/'installation.json').read_text())
    if record['phase'] != 'awaiting_live_check':
        raise ValueError('Not awaiting live check')
    control('is-active', BASE.name+'-server.service')
    control('stop', record['rollback_unit']+'.timer')
    write_json(stage/'installation.json', dict(record, phase='committed'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser();parser.add_argument('action', choices=('install','rollback','commit'))
    args = parser.parse_args();stage = Path(__file__).resolve().parent
    if os.geteuid() != 0 or stage.parent != Path('/home/xilinx') or not stage.name.startswith('gl-unified-inputs-20261013-'):
        raise ValueError('Use this board-local private stage as root')
    plan = json.loads((stage/'deployment-plan.json').read_text())
    helper = Path(plan['installer_helper'])
    # Keep the established atomic replacement and service-control implementation.
    import hashlib
    if hashlib.sha256(helper.read_bytes()).hexdigest() != plan['installer_helper_sha']:
        raise ValueError('Shared installation helper differs')
    sys.path.insert(0, str(helper.parent))
    from install_calibration_repair import sha, replace, control, write_json
    globals()[args.action](stage, plan)
    print(json.dumps(json.loads((stage/'installation.json').read_text())), flush=True)
