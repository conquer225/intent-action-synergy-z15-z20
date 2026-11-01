"""Control the existing ARM raw recorder for a linked, manually cued diagnostic."""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import shlex
import time

from run_soak_stage import ROOT, PROD, connect, command
from run_mi_arm_acceptance import dump

OUT = ROOT/'eeg_apps_z15/output/ssvep_raw_sync_20261002'
PROTOCOL = ROOT/'eeg_apps_z15/ssvep_diagnostic_protocol.json'
LEDGER = OUT/'diagnostic_recording.json'
FILES = ('metadata.json','samples_i32le.bin','sequence_u8.bin','flags_u8.bin',
         'stream_index_u64le.bin','arrival_mono_f64le.bin','window_results.jsonl')


REMOTE_COMMON = '''import json, pathlib, urllib.request, time, secrets
from cyton_trial_recorder import atomic_json, read_json, CONTROL_PATH, STATUS_PATH
def api(path):
 with urllib.request.urlopen('http://127.0.0.1:9102'+path,timeout=5) as r:return json.load(r)
def wait_for(command_id):
 for _ in range(24):
  state=read_json(STATUS_PATH)
  if state.get('last_command')==command_id:return state
  time.sleep(.25)
 raise RuntimeError('Recorder did not acknowledge; inspect status before retrying')
'''


def remote(client, code):
    return json.loads(command(client, 'cd '+shlex.quote(PROD)+' && python3 -c '+shlex.quote(REMOTE_COMMON+code)))


def start(client, capture_kind='six_cued_trials'):
    if LEDGER.exists():
        raise ValueError('This diagnostic already has a ledger; inspect it instead of overwriting')
    raw = PROTOCOL.read_bytes()
    protocol = json.loads(raw)
    if capture_kind == 'format_smoke':
        protocol=dict(protocol,requested_targets_hz=[],purpose='Verify raw format and alignment only; no visual stimulus')
    payload = dict(action='start',id=None,trial_id=None,participant_id='SSVEP01',
        task='ssvep',phase='ssvep_diagnostic',condition='ssvep_cued_diagnostic',
        stimulus_note='Manually cued 10/rest/12/rest/10/12; no emotion labels',
        protocol=protocol,
        protocol_digest=hashlib.sha256(json.dumps(protocol,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        cue_log_path=PROD+'/ssvep_cued_trials.jsonl')
    payload['stimulus_note']=capture_kind
    code = '''cue=api('/api/ssvep-cue')
state=read_json(STATUS_PATH)
telemetry=api('/api/telemetry')
if cue.get('raw_recording_supported') is not True:raise ValueError('Raw-sync runtime not installed')
if cue.get('state') in ('active','awaiting_presentation'):raise ValueError('Stop the current cue before arming raw capture')
if state.get('state')=='recording':raise ValueError('Another recording is active')
pending=read_json(CONTROL_PATH)
if pending.get('id') and pending['id']!=state.get('last_command'):raise ValueError('A recording command is still pending')
if telemetry.get('stale') or not telemetry.get('telemetry',{}).get('real'):raise ValueError('Real Cyton input is not fresh')
payload=PAYLOAD
payload.update(id=secrets.token_hex(8),trial_id=secrets.token_hex(8))
atomic_json(CONTROL_PATH,payload)
state=wait_for(payload['id'])
if state.get('state')!='recording' or state.get('task')!='ssvep':raise RuntimeError('Raw capture rejected: '+str(state))
for _ in range(24):
 state=read_json(STATUS_PATH)
 if state.get('state')!='recording':raise RuntimeError('Capture ended before readiness: '+str(state))
 if state.get('samples',0)>=250 and (pathlib.Path(state['path'])/'samples_i32le.bin').stat().st_size>=8000:break
 time.sleep(.25)
else:raise RuntimeError('No verified raw buffer; inspect capture before starting a cue')
print(json.dumps({'command':payload,'state':state,'cue':api('/api/ssvep-cue'),
 'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()}))
'''.replace('PAYLOAD',repr(payload))
    result = remote(client, code)
    dump(LEDGER,dict(pc_local_started=datetime.now().isoformat(),**result))
    print(json.dumps(result,ensure_ascii=False))


def status(client):
    print(json.dumps(remote(client, '''print(json.dumps({'recording':read_json(STATUS_PATH),
 'cue':api('/api/ssvep-cue'),'ssvep':api('/api/ssvep-shadow').get('live')}))
'''),ensure_ascii=False))


def stop(client):
    trial_id=json.loads(LEDGER.read_text())['state']['trial_id']
    result=remote(client, '''state=read_json(STATUS_PATH)
cue=api('/api/ssvep-cue')
if cue.get('state') in ('active','awaiting_presentation'):raise ValueError('Finish or stop the current cue first')
if state.get('state')!='recording' or state.get('trial_id')!=TRIAL:raise ValueError('No matching active diagnostic recording')
payload=dict(id=secrets.token_hex(8),action='stop',trial_id=TRIAL)
atomic_json(CONTROL_PATH,payload)
state=wait_for(payload['id'])
if state.get('state')!='complete':raise RuntimeError('Raw capture did not close: '+str(state))
print(json.dumps(state))
'''.replace('TRIAL',repr(trial_id)))
    dump(OUT/'recording_stop.json',dict(pc_local_stopped=datetime.now().isoformat(),state=result))
    print(json.dumps(result,ensure_ascii=False))


def collect(client):
    import struct
    saved=json.loads(LEDGER.read_text())
    trial_id=saved['state']['trial_id']
    path=saved['state']['path']
    if path!=PROD+'/recordings/'+trial_id or len(trial_id)!=16 or any(c not in '0123456789abcdef' for c in trial_id):
        raise ValueError('Recording path/ID mismatch')
    local=OUT/'recordings'/trial_id
    local.mkdir(parents=True,exist_ok=False)
    with client.open_sftp() as s:
        for name in FILES:s.get(path+'/'+name,str(local/name))
        s.get(PROD+'/ssvep_cued_trials.jsonl',str(local/'cue_audit_original.jsonl'))
    metadata=json.loads((local/'metadata.json').read_text())
    if metadata.get('state') not in ('complete','duration_limit','service_stopped'):
        raise ValueError('Do not evaluate an unfinished capture')
    count=metadata['samples']
    lengths={name:(local/name).stat().st_size for name in FILES}
    expected={'samples_i32le.bin':32*count,'sequence_u8.bin':count,'flags_u8.bin':count,
              'stream_index_u64le.bin':8*count,'arrival_mono_f64le.bin':8*count}
    if not count or any(lengths[name]!=size for name,size in expected.items()):
        raise ValueError('Raw data/alignment lengths disagree; preserve for recovery')
    indices=struct.unpack('<%dQ'%count,(local/'stream_index_u64le.bin').read_bytes())
    if any(b!=a+1 for a,b in zip(indices,indices[1:])):
        raise ValueError('Service packet index continuity failed')
    arrivals=struct.unpack('<%dd'%count,(local/'arrival_mono_f64le.bin').read_bytes())
    if any(not math.isfinite(value) or value<0 for value in arrivals):
        raise ValueError('Receive timestamp invalid')
    if any(b<a for a,b in zip(arrivals,arrivals[1:])):
        raise ValueError('Receive timestamp moved backwards')
    sequences=(local/'sequence_u8.bin').read_bytes()
    flags=(local/'flags_u8.bin').read_bytes()
    if any(bool(flags[i]&1) != (((sequences[i]-sequences[i-1])&255)!=1)
           for i in range(1,count)):
        raise ValueError('Raw sequence discontinuity flags disagree')
    rows=[json.loads(line) for line in (local/'cue_audit_original.jsonl').read_text().splitlines()]
    linked=[row for row in rows if row.get('raw_recording_id')==trial_id]
    (local/'linked_cue_events.jsonl').write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in linked),encoding='utf-8')
    summary=dict(raw_integrity_passed=True,samples=count,metadata=metadata,lengths=lengths,
        arrival_span_seconds=arrivals[-1]-arrivals[0],
        sequence_discontinuities=sum(bool(value&1) for value in flags),
        cue_events=len(linked),all_attempts_started=[row['target_hz'] for row in linked if row['event']=='trial_start'],
        sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in local.iterdir() if p.is_file()},
        optical_onset_verified=False,recognition_accuracy_not_claimed=True)
    dump(local/'capture_audit.json',summary)
    print(json.dumps(dict(path=str(local),samples=count,cue_events=len(linked),raw_integrity_passed=True)))


def main():
    global LEDGER
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('start','status','stop','collect','smoke'))
    args=parser.parse_args()
    c=connect()
    try:
        if args.action=='smoke':
            LEDGER=OUT/'smoke_recording.json'
            start(c,capture_kind='format_smoke')
            time.sleep(2)
            stop(c)
            collect(c)
        else:
            {'start':start,'status':status,'stop':stop,'collect':collect}[args.action](c)
    finally:c.close()


if __name__=='__main__':main()
