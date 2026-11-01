"""Exercise installed navigation through its manual API, without sensor fixtures."""
import json
from pathlib import Path
import time

import drive_navigation_apply as app


def wait_page(page):
    deadline=time.monotonic()+14
    while True:
        row=app.api();player=row['player'];system=player.get('system') or {}
        if player.get('state')=='error':raise RuntimeError(player.get('error'))
        if system.get('page')==page and system.get('reading') is False:return row
        if time.monotonic()>deadline:raise TimeoutError('Page did not settle: '+page)
        time.sleep(.25)


def choose(region,page):
    app.api({'action':'choose','value':region})
    return wait_page(page)


def main():
    stage=Path(__file__).resolve().parent
    report={'source':'manual_web_controls_no_eeg_or_gaze_simulation','checks':[]}
    before=app.control('show','guardianloop-cyton.service','-p','MainPID','--value')
    try:
        wait_page('home');choose(0,'speed');choose(1,'drive')
        deadline=time.monotonic()+12
        while True:
            row=app.api();system=row['player']['system'];hdmi=system['hdmi_stimulus']
            if hdmi['active'] and (hdmi.get('timing') or {}).get('ready') is True:break
            if hdmi.get('error'):raise RuntimeError(hdmi['error'])
            if time.monotonic()>deadline:raise TimeoutError('Automatic scan did not qualify')
            time.sleep(.25)
        if hdmi['display_only'] is not True or hdmi['votes']['unique_windows']!=0:
            raise ValueError('Offline scan claimed EEG')
        if system['physical_output_enabled'] is not False:raise ValueError('Physical output changed')
        report['checks'].append({'name':'automatic_direction_no_eeg','hdmi':hdmi,'labels':system['labels']})
        row=choose(1,'home')
        if row['player']['system']['hdmi_stimulus']['active']:raise ValueError('Scan continued after return')
        report['checks'].append({'name':'centre_return_stops_scan','page':'home','active':False})
        choose(2,'media');choose(0,'video');row=choose(0,'video_nav')
        if row['player']['system']['labels']!=['上一条','返回主页','下一条']:
            raise ValueError('Navigation labels differ')
        initial=row['player']['system']['video_index']
        row=choose(0,'video');previous=row['player']['system']['video_index']
        choose(0,'video_nav');row=choose(2,'video');following=row['player']['system']['video_index']
        if following!=initial:raise ValueError('Previous and next are no longer symmetric')
        choose(0,'video_nav');choose(1,'home')
        report['checks'].append({'name':'video_navigation_home_previous_next',
            'initial_index':initial,'previous_index':previous,'following_index':following})
        after=app.control('show','guardianloop-cyton.service','-p','MainPID','--value')
        if after!=before:raise RuntimeError('Acquisition changed')
        report.update(passed=True,acquisition_pid=after)
    except BaseException as error:
        report.update(passed=False,error=str(error))
        raise
    finally:
        app.api({'action':'home'});row=wait_page('home');player=row['player'];system=player['system']
        report['final']={'session_id':player['session_id'],'state':player['state'],
            'page':system['page'],'eye':system['eye'],'hdmi_stimulus':system['hdmi_stimulus'],
            'physical_output_enabled':system['physical_output_enabled']}
        (stage/'navigation-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
