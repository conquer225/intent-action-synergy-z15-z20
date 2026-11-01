"""Passive post-repair checks; no start, display, recording, or device commands."""
import argparse
from collections import Counter
import json
from pathlib import Path
import shlex

from run_soak_stage import connect, command
from run_mi_arm_acceptance import dump


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=40)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 5<=args.seconds<=55:
        raise ValueError('Observation must be 5..55 seconds')
    probe="""import json,pathlib,time,urllib.request,subprocess
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def units():
    return subprocess.check_output(['systemctl','show','guardianloop-cyton.service','guardianloop-web.service','-p','Id','-p','MainPID','-p','ActiveState','-p','NRestarts']).decode()
before=units();rows=[];began=time.monotonic()
while time.monotonic()-began < SECONDS:
    start=time.monotonic();row={}
    try:
        with opener.open('http://127.0.0.1:9102/api/ssvep-free',timeout=3) as response:
            s=json.load(response)
        row.update(request_ms=(time.monotonic()-start)*1000,input=s.get('input'),state=s.get('state'),accepted=s.get('accepted'))
        p=json.loads(pathlib.Path('/tmp/guardianloop-ssvep-shadow.json').read_text())
        row.update(producer_age_ms=p.get('input_age_seconds',0)*1000,sequence_gaps=p.get('sequence_gaps'),packets_seen=p.get('packets_seen'))
    except (OSError,ValueError) as exc:
        row['error']=str(exc)
    rows.append(row);time.sleep(max(0,1-(time.monotonic()-start)))
print(json.dumps(dict(before=before,after=units(),rows=rows,source='passive_live_status',human_accuracy_measured=False)))
""".replace('SECONDS',str(args.seconds))
    client=connect()
    try:
        result=json.loads(command(client,"/usr/local/share/pynq-venv/bin/python3 -c "+shlex.quote(probe)))
    finally:
        client.close()
    rows=result['rows']
    def distribution(values):
        values=sorted(values)
        return dict(n=len(values),median=values[len(values)//2],p95=values[int((len(values)-1)*.95)],maximum=max(values)) if values else None
    summary=dict(samples=len(rows),errors=sum('error' in r for r in rows),
        ready=sum((r.get('input') or {}).get('ready') is True for r in rows),
        input_states=dict(Counter((r.get('input') or {}).get('state','error') for r in rows)),
        producer_ms=distribution([r['producer_age_ms'] for r in rows if 'producer_age_ms' in r]),
        endpoint_ms=distribution([r['request_ms'] for r in rows if 'request_ms' in r]),
        endpoint_input_ms=distribution([r['input']['age_seconds']*1000 for r in rows if (r.get('input') or {}).get('age_seconds') is not None]),
        services_unchanged=result['before']==result['after'],
        sequence_gaps=[r.get('sequence_gaps') for r in rows],
        active_sessions=sum(r.get('state') in ('active','awaiting_presentation') for r in rows))
    result['summary']=summary
    dump(args.output,result)
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    main()
