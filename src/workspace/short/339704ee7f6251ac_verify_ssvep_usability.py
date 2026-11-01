"""Board-local, non-flashing raw-capture smoke and passive input checks."""
import json
from pathlib import Path
import shlex
import sys

sys.path.append(r'D:\Users\lenovo\anaconda3\Lib\site-packages')
from run_soak_stage import connect, command

OUT=Path(__file__).parent/'output/ssvep_usability_20261003'
REMOTE=r'''
import json,time,pathlib,urllib.request,hashlib,struct
base='http://127.0.0.1:9102'
def api(payload=None):
    request=urllib.request.Request(base+'/api/ssvep-cue',
        data=json.dumps(payload).encode() if payload else None,
        headers={'Content-Type':'application/json','Origin':base} if payload else {})
    with urllib.request.urlopen(request,timeout=3) as response:return json.load(response)
result={'screen_flashing':False,'physical_control':False,'smoke':{},'passive':[]}
current=api()
if current['state'] in ('active','awaiting_presentation'):
    raise RuntimeError('Human cued trial active; refuse smoke')
with urllib.request.urlopen(base+'/api/ssvep-free',timeout=3) as response:free=json.load(response)
if free['state'] in ('active','awaiting_presentation'):
    raise RuntimeError('Human free trial active; refuse smoke')
if current.get('raw_recording') or current.get('recording_control',{}).get('owned_trial_id'):
    raise RuntimeError('Existing recording; refuse smoke')
for attempt in range(15):
    current=api()
    if current.get('input',{}).get('ready'):break
    time.sleep(.5)
if not current.get('input',{}).get('ready'):
    result['smoke']={'state':'not_run','reason':'input_quality_or_freshness_not_ready','input':current.get('input')}
else:
    opened=False
    try:
        requested=api({'action':'record_start','target_hz':0,'consent':True})
        opened=True
        result['smoke']['request']=requested.get('recording_control')
        for attempt in range(32):
            current=api({'action':'record_status'})
            if current.get('recording_control',{}).get('state')=='ready':break
            time.sleep(.25)
        if current.get('recording_control',{}).get('state')!='ready':
            raise RuntimeError('Raw preparation did not become ready')
        context=current['raw_recording']
        result['smoke']['context']=context
        assert current['state'] not in ('active','awaiting_presentation')
        time.sleep(1)
    finally:
        if opened:
            api({'action':'record_cancel'})
            for attempt in range(24):
                current=api({'action':'record_status'})
                if current.get('recording_control',{}).get('state')=='complete':break
                time.sleep(.25)
            result['smoke']['closed']=current.get('recording_control')
    if current.get('recording_control',{}).get('state')!='complete':
        raise RuntimeError('Raw close not acknowledged')
    path=pathlib.Path(context['path']).resolve()
    root=pathlib.Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq/recordings').resolve()
    assert path.parent==root and path.name==context['trial_id']
    meta=json.loads((path/'metadata.json').read_text())
    assert meta['state']=='complete' and meta['task']=='ssvep' and meta['samples']>=250
    sizes={'samples_i32le.bin':32,'sequence_u8.bin':1,'flags_u8.bin':1,
           'stream_index_u64le.bin':8,'arrival_mono_f64le.bin':8}
    file_checks={}
    for name,width in sizes.items():
        raw=(path/name).read_bytes()
        assert len(raw)==meta['samples']*width
        file_checks[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    arrival=struct.unpack('<%dd'%meta['samples'],(path/'arrival_mono_f64le.bin').read_bytes())
    assert all(b>=a for a,b in zip(arrival,arrival[1:]))
    result['smoke'].update(state='passed',metadata=meta,files=file_checks,
                          raw_capture_completeness_verified=False,stimulus_presented=False)
for n in range(30):
    current=api()
    result['passive'].append({'input':current.get('input'), 'state':current['state'],
                             'recording_control':current.get('recording_control')})
    time.sleep(.5)
print(json.dumps(result,ensure_ascii=False,allow_nan=False))
'''

def main():
    client=connect()
    try:
        result=json.loads(command(client,'/usr/local/share/pynq-venv/bin/python3 -c '+shlex.quote(REMOTE)))
        (OUT/'nonflashing_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(dict(smoke=result['smoke']['state'],
            samples=result['smoke'].get('metadata',{}).get('samples'),
            input_states=[r['input']['state'] for r in result['passive']],screen_flashing=False),ensure_ascii=False))
    finally:client.close()

if __name__=='__main__':main()
