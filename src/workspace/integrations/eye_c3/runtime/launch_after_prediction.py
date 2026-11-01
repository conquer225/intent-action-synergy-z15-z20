"""PC-only recorded-workload launch; not a unittest or live EEG test."""
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

import stage_server as upload
from stage_media import STATE


def main():
    state=json.loads(STATE.read_text());client=upload.trial.connect('192.168.2.99')
    started=time.monotonic()
    try:
        while time.monotonic()-started<60:
            row=json.loads(upload.trial.execute(client,'tail -n 1 '+state['remote']+'/eeg-compact-load/monitor.jsonl'))
            primary=row.get('primary',{})
            if primary.get('valid') is True and primary.get('emotion_valid') is True:
                request=Request('http://192.168.2.99:9117/api/player',
                    data=json.dumps(dict(action='play',id='fixture60compact')).encode(),
                    headers={'X-Media-Key':state['key'],'Content-Type':'application/json'},method='POST')
                with urlopen(request,timeout=20) as response:result=json.load(response)
                destination=Path(__file__).resolve().parent/'output/long_cache_20261007/compact_joint_launch.json'
                destination.write_text(json.dumps(dict(replay_observation=row,player=result)))
                print(json.dumps(dict(started_after_prediction=True,player=result)),flush=True);return
            print(json.dumps(dict(elapsed=row.get('elapsed_seconds'),primary=primary)),flush=True)
            time.sleep(2)
        raise TimeoutError('No accepted emotion+fatigue prediction within finite wait; no display started')
    finally:client.close()


if __name__=='__main__':main()
