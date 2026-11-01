"""Checksummed web-only update; keep the current HDMI and acquisition owners."""
import json
from pathlib import Path
import shutil
import time

import drive_navigation_apply as app
from install_calibration_repair import replace,sha,write_json

NAMES={'media_server.py','wheelchair_link.py','system_mobile.js','system_mobile.html','boot-pins.json'}


def main():
    stage=Path(__file__).resolve().parent
    if stage.parent!=Path('/home/xilinx') or not stage.name.startswith(('gl-phone-manual-20261014-','gl-motor-test-20261015-')):
        raise ValueError('Use the private phone update stage')
    plan=json.loads((stage/'plan.json').read_text())
    if plan['boot']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip() or not plan['tests_passed']:
        raise ValueError('Update boot or tests changed')
    expected={app.BASE/name for name in NAMES}
    if plan.get('motor_test_update') is True:
        expected.update((app.BASE/'media_state.json',app.BASE/'system_runtime/wheelchair_ssvep/bench_network_bridge.py'))
    if {Path(item['target']) for item in plan['files']}!=expected:
        raise ValueError('Unexpected web update targets')
    for item in plan['files']:
        target=Path(item['target'])
        if target.is_symlink() or sha(target)!=item['old_sha'] or sha(stage/'payload'/item['key'])!=item['new_sha']:
            raise ValueError('Update artifact changed')
    before=app.api()['player'];session=before['session_id']
    before_pid=app.control('show',session+'.service','-p','MainPID','--value')
    acquisition=app.control('show','guardianloop-cyton.service','-p','MainPID','--value')
    backup=stage/'backup';backup.mkdir(mode=0o700)
    for item in plan['files']:shutil.copy2(item['target'],backup/item['key'])
    result={'display_session':session,'display_pid':before_pid,'acquisition_pid':acquisition,
            'display_restarted':False,'pl_reloaded':False,'motor_enabled':plan.get('motor_test_update') is True}
    app.stop_server()
    try:
        for item in plan['files']:replace(stage/'payload'/item['key'],Path(item['target']),item['mode'])
        pins=json.loads((app.BASE/'boot-pins.json').read_text())['files']
        if any(sha(Path(path))!=digest for path,digest in pins.items()):raise ValueError('Boot pins differ')
        app.start_server();deadline=time.monotonic()+15
        while True:
            try:row=app.api();break
            except OSError:
                if time.monotonic()>deadline:raise
                time.sleep(.2)
        if row['player']['session_id']!=session:raise ValueError('Display session changed')
        if app.control('show',session+'.service','-p','MainPID','--value')!=before_pid:
            raise ValueError('Display process changed')
        if app.control('show','guardianloop-cyton.service','-p','MainPID','--value')!=acquisition:
            raise ValueError('Acquisition process changed')
        result.update(state='installed',boot_pins=len(pins))
    except BaseException as error:
        result.update(state='rolled_back',error=str(error));app.stop_server()
        for item in plan['files']:
            target=Path(item['target']);old=backup/item['key']
            if sha(old)!=item['old_sha'] or sha(target) not in (item['old_sha'],item['new_sha']):
                raise ValueError('Refuse to overwrite a later edit')
            replace(old,target,item['mode'])
        app.start_server()
        raise
    finally:
        write_json(stage/'installation.json',result)
        print(json.dumps(result),flush=True)


if __name__=='__main__':main()
