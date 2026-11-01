"""Bounded manual-input acceptance of the private API, never EEG/gaze simulation."""
import argparse
import json
from pathlib import Path
import time
from urllib.request import Request,build_opener,ProxyHandler

from stage_media import STATE


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('menus','fps'))
    args=parser.parse_args();stage=json.loads(STATE.read_text());opener=build_opener(ProxyHandler({}))
    url='http://192.168.2.99:9117/api/player';checks=[];session=None
    def api(body=None):
        headers={'X-Media-Key':stage['key']}
        if body is not None:headers['Content-Type']='application/json'
        with opener.open(Request(url,data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers),timeout=5) as response:return json.load(response)
    def wait(predicate,limit=20):
        deadline=time.monotonic()+limit
        while time.monotonic()<deadline:
            row=api();player=row['player']
            if player.get('session_id') not in (None,session):raise RuntimeError('Private session changed; do not touch replacement')
            if player.get('state')=='error':raise RuntimeError(player.get('error','Display failed'))
            if predicate(row):return row
            time.sleep(.25)
        raise TimeoutError('Private display did not acknowledge within deadline')
    def page(name):
        row=wait(lambda r:r['player'].get('system',{}).get('page')==name and not r['player']['system']['reading'])
        sys=row['player']['system'];assert sys['physical_output_enabled'] is False
        checks.append(dict(page=name,speed=sys['speed_level'],direction=sys['direction'],manual_test=True))
        print('ACK',name,sys['speed_level'],sys['direction'],flush=True);return row
    try:
        if args.mode=='menus':
            row=api();session=row['player'].get('session_id')
            if row['player'].get('state')!='playing' or not session:raise ValueError('Expected active SD portrait session')
            api({'action':'home'});page('home')
            api({'action':'choose','value':0});row=page('speed');assert row['player']['system']['speed_level']==1
            api({'action':'choose','value':0});wait(lambda r:(r['player'].get('system') or {}).get('speed_level')==2)
            api({'action':'choose','value':1});row=page('drive');assert row['player']['system']['speed_level']==2
            api({'action':'choose','value':2});page('media')
            api({'action':'choose','value':0});page('video')
            api({'action':'choose','value':2});page('video_rate')
            api({'action':'choose','value':1});page('video')
            api({'action':'choose','value':0});page('video_nav')
            api({'action':'choose','value':1});page('video')
            api({'action':'eye_start'})
            row=wait(lambda r:((r['player'].get('system') or {}).get('eye') or {}).get('state') in ('prepare','settle','failed'),limit=15)
            eye=row['player']['system']['eye'];checks.append(dict(eye=eye));print('EYE',eye,flush=True)
            assert eye['valid'] is False and eye['calibrated'] is False
            api({'action':'eye_stop'});wait(lambda r:not (r['player'].get('system') or {}).get('eye'))
        else:
            result=api({'action':'play','id':'afbb05f8cef54ef9a7ddadbf2613b0e6'});session=result['session_id']
            row=wait(lambda r:r['player'].get('state')=='playing');start_frame=row['player']['frame'];start=time.monotonic()
            buffering_polls=0
            while time.monotonic()-start<40:
                row=api();assert row['player'].get('session_id')==session
                assert row['player']['state'] in ('playing','buffering'),row['player']
                assert not row['player']['system']['physical_output_enabled']
                if row['player']['state']=='buffering':buffering_polls+=1
                time.sleep(1)
            checks.append(dict(wall_s=time.monotonic()-start,new_frames=row['player']['frame']-start_frame,
                               buffering_polls=buffering_polls,brain=row['brain'],eye=row['player']['system'].get('eye')))
        api({'action':'stop'});wait(lambda r:r['player'].get('state')=='stopped' and r['player'].get('original_restored') is True)
        checks.append({'controlled_stop':True,'original_restored':True})
    finally:
        if session:
            row=api()
            if row['player'].get('session_id')==session and row['player'].get('state') in ('playing','menu','buffering','paused'):
                api({'action':'stop'})
        out=Path(__file__).with_name('output')/'live_system_20261007';out.mkdir(parents=True,exist_ok=True)
        (out/(args.mode+'-acceptance.json')).write_text(json.dumps(dict(session=session,checks=checks),indent=2),encoding='utf-8')
    print('PRIVATE_ACCEPTANCE_COMPLETE',args.mode,session,flush=True)


if __name__=='__main__':main()
