"""Read-only board evidence for recording readiness and free-selection gates."""
import json
from pathlib import Path
import shlex
import sys

sys.path.append(r'D:\Users\lenovo\anaconda3\Lib\site-packages')
from run_soak_stage import connect, command

OUT = Path(__file__).parent/'output/ssvep_usability_20261003_audit'
APP = '/home/xilinx/jupyter_notebooks/guardianloop_pynq'
REMOTE = r'''
import json,time,collections,pathlib,urllib.request
app=pathlib.Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
result={'snapshots':[], 'logs':{}}
for n in range(12):
    row={}
    for endpoint in ('ssvep-free','ssvep-cue','ssvep-shadow','recording'):
        try:
            with urllib.request.urlopen('http://127.0.0.1:9102/api/'+endpoint,timeout=3) as response:
                row[endpoint]=json.load(response)
        except (OSError,ValueError) as error:
            row[endpoint]={'error':str(error)}
    result['snapshots'].append(row)
    time.sleep(.5)
for filename in ('ssvep_free_events.jsonl','ssvep_cued_trials.jsonl'):
    p=app/filename
    if not p.exists():continue
    with p.open('rb') as f:
        f.seek(max(0,p.stat().st_size-4000000))
        if f.tell():f.readline()
        rows=[]
        for line in f:
            try:rows.append(json.loads(line))
            except ValueError:pass
    result['logs'][filename]={'size':p.stat().st_size,'rows':rows}
result['record_status']=json.loads(pathlib.Path('/run/guardianloop/recording_status.json').read_text())
print(json.dumps(result,ensure_ascii=False,allow_nan=False))
'''

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    client=connect()
    try:
        raw=command(client,'/usr/local/share/pynq-venv/bin/python3 -c '+shlex.quote(REMOTE))
        data=json.loads(raw)
        (OUT/'board_audit.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        print('snapshots',len(data['snapshots']))
        print('input states',[r['ssvep-free'].get('input',{}).get('state') for r in data['snapshots']])
        for name,log in data['logs'].items():
            print(name,'bytes',log['size'],'rows',len(log['rows']))
            if name.startswith('ssvep_free'):
                starts=[r for r in log['rows'] if r.get('event')=='start'][-8:]
                for start in starts:
                    session=[r for r in log['rows'] if r.get('id')==start['id']]
                    print(json.dumps(dict(id=start['id'],frequencies=start['frequencies'],
                        counts={kind:sum(r.get('event')==kind for r in session)
                                for kind in ('heartbeat','candidate','window_diagnostic')},
                        frame_ok=sum(r.get('frame_ok') is True for r in session)),ensure_ascii=False))
            else:
                print('last event',log['rows'][-1].get('event'))
    finally:client.close()

if __name__=='__main__':main()
