"""Finite silent control check; not an FPS benchmark or real-phone UX test."""
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

from stage_media import STATE
import stage_server as upload


def main():
    state=json.loads(STATE.read_text())
    def request(body=None):
        req=Request('http://192.168.2.99:9117/api/player',
            data=json.dumps(body).encode() if body else None,
            headers={'X-Media-Key':state['key'],'Content-Type':'application/json'})
        with urlopen(req,timeout=8) as response:return json.load(response)
    def until(predicate,seconds=15):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            value=request()['player']
            if predicate(value):return value
            if value.get('state')=='error':raise RuntimeError(value.get('error'))
            time.sleep(.3)
        raise TimeoutError('Finite player control wait expired')
    result={'scope':'Real private HDMI player API, PC client; not phone UX or FPS acceptance',
            'audio_output':False,'physical_control':False}
    ident=None
    try:
        launched=request(dict(action='play',id='fixture60compact'));ident=launched['session_id']
        result['session_id']=ident
        until(lambda s:s.get('session_id')==ident and s.get('frame',0)>=3)
        request(dict(action='pause'))
        paused=until(lambda s:s.get('state')=='paused')
        time.sleep(.7);still=request()['player']
        result['paused_frame_stable']=still['state']=='paused' and still['frame']==paused['frame']
        request(dict(action='resume'))
        advanced=until(lambda s:s.get('state')=='playing' and s['frame']>paused['frame'])
        result['resume_advanced']=advanced['frame']>paused['frame']
        request(dict(action='stop'))
        stopped=until(lambda s:s.get('state')=='stopped',20)
        result['controlled_stop_restored']=stopped.get('original_restored') is True
        result['passed']=all(result[k] for k in ('paused_frame_stable','resume_advanced','controlled_stop_restored'))
    finally:
        if ident:
            current=request()['player']
            if current.get('session_id')==ident and current.get('state') not in ('stopped','complete','error'):
                request(dict(action='stop'))
        output=Path(__file__).resolve().parent/'output/long_cache_20261007/player_controls.json'
        output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    client=upload.trial.connect('192.168.2.99')
    try:
        with client.open_sftp() as sftp:
            sftp.get(state['remote']+'/'+ident+'-report.json',str(output.with_name(ident+'-report.json')))
    finally:client.close()
    print(json.dumps(result,ensure_ascii=False))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
