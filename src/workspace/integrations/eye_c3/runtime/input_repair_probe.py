"""Short, non-flashing observation of formal input preparation and withdrawal."""
import argparse
import hashlib
import json
from pathlib import Path
import threading
import time
from urllib.request import Request,urlopen


def request(port,path,body=None):
    base='http://127.0.0.1:'+str(port)
    headers={'Origin':base,'Content-Type':'application/json'}
    with urlopen(Request(base+path,data=json.dumps(body).encode() if body else None,
                         headers=headers),timeout=3) as response:return json.load(response)


def checkpoint():
    path=Path('/run/guardianloop/calibration-session.json')
    row=json.loads(path.read_text())
    return dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                fatigue_windows=len(row['fatigue']['baseline']),
                sqi_reference_counts=[len(v) for v in row['sqi']['reference']])


def observe_page(stopped, rows):
    page=Path('/dev/shm/gl-hdmi-live-20261008-ea117349-system-page.json')
    request_path=page.with_name(page.name+'.browser-input')
    while not stopped.is_set():
        now=time.monotonic()
        row=dict(at=now)
        for name,path in (('hdmi_page',page),('browser_request',request_path)):
            try:
                value=json.loads(path.read_text())
                row[name]=dict(age=now-value['updated_monotonic'],
                    mode=value['mode'],enabled=value.get('enabled'),page=value.get('page'))
            except (OSError,ValueError,KeyError) as exc:row[name]=dict(error=str(exc))
        rows.append(row)
        stopped.wait(.1)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=dict(before=checkpoint(),rows=[],errors=[],page_observations=[])
    stopped=threading.Event()
    observer=threading.Thread(target=observe_page,args=(stopped,result['page_observations']))
    observer.start()
    token=None
    try:
        prepared=request(9105,'/api/ssvep-free',{'action':'input_prepare','consent':True})
        token=prepared['input']['preparation']['token']
        if not token:raise ValueError('Preparation lease was not granted')
        began=time.monotonic()
        for _ in range(24):
            tick=time.monotonic()
            try:
                v=request(9105,'/api/ssvep-free',{'action':'input_heartbeat','token':token})
                f=request(9102,'/api/status')['fatigue']
                telemetry=request(9102,'/api/telemetry')['telemetry']
                q=telemetry['sqi'] or {}
                channels=q.get('channels') or []
                c=channels[1] if len(channels)>1 else {}
                i=v['input']
                result['rows'].append(dict(elapsed=round(tick-began,3),
                    input={k:i.get(k) for k in ('ready','state','reason','age_seconds','warmup_samples')},
                    primary={k:f.get(k) for k in ('state','reason','calibration_current','calibration_retained',
                        'input_age_at_prediction_seconds','packets_seen')},
                    ch2={k:c.get(k) for k in ('quality','usable','reasons','mains_ratio')},
                    runtime=telemetry['runtime'],
                    stimulus_state=v['state'],accepted=v['accepted']))
            except (OSError,ValueError,KeyError,IndexError) as exc:
                result['errors'].append(str(exc))
            time.sleep(max(0,1-(time.monotonic()-tick)))
        request(9105,'/api/ssvep-free',{'action':'input_release','token':token});token=None
        time.sleep(3.5)
        released=request(9105,'/api/ssvep-free')
        result['after_release']={k:released['input'].get(k) for k in ('state','reason','age_seconds','ready')}
    finally:
        if token:
            try:request(9105,'/api/ssvep-free',{'action':'input_release','token':token})
            except OSError as exc:result['errors'].append('Release: '+str(exc))
        stopped.set();observer.join(timeout=2)
        if observer.is_alive():raise RuntimeError('Page observer did not finish')
        result['after']=checkpoint()
        args.output.write_text(json.dumps(result,indent=2));args.output.chmod(0o600)
    print(json.dumps(dict(samples=len(result['rows']),errors=result['errors'],
                         calibration_preserved=result['before']==result['after'],
                         after_release=result.get('after_release'))),flush=True)


if __name__=='__main__':main()
