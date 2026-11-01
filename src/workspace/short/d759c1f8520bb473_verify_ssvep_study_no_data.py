"""Check deployed free-SSVEP refusal without creating a study or recording."""
import json
from pathlib import Path
import shlex

from run_soak_stage import connect, command

OUT = Path(__file__).resolve().parent/'output/ssvep_free_study_20261003/no_data_refusal.json'
PROBE = r'''
import hashlib,json,pathlib,urllib.request,urllib.error
root=pathlib.Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
control=pathlib.Path('/home/xilinx/.guardianloop_record_command.json')
url='http://127.0.0.1:9102/api/ssvep-free'
def files():
 return dict(command_sha256=hashlib.sha256(control.read_bytes()).hexdigest() if control.exists() else None,
  recordings=sorted(p.name for p in (root/'recordings').iterdir()) if (root/'recordings').exists() else [],
  studies=sorted(p.name for p in (root/'ssvep_studies').iterdir()) if (root/'ssvep_studies').exists() else [])
def state():
 with urllib.request.urlopen(url,timeout=3) as r:return json.load(r)
before=state()
if before.get('input',{}).get('state')!='no_data' or before.get('state')!='idle':
 raise RuntimeError('Requires idle/no-data production state; no commands sent')
original=files();responses=[]
for action in ('record_start','start'):
 payload=dict(action=action,consent=True,frequencies=[8,10,12,14],require_raw_recording=True)
 req=urllib.request.Request(url,data=json.dumps(payload).encode(),method='POST',
  headers={'Content-Type':'application/json','Origin':'http://127.0.0.1:9102'})
 try:
  with urllib.request.urlopen(req,timeout=3) as r:code,body=r.status,json.load(r)
 except urllib.error.HTTPError as e:code,body=e.code,json.load(e)
 responses.append(dict(action=action,http_status=code,body=body))
after=state();unchanged=files()==original
passed=(all(r['http_status']==400 and 'O1/O2' in r['body'].get('error','') for r in responses)
 and unchanged and after.get('state')=='idle' and after.get('result') is None
 and after.get('accepted') is False and after.get('study',{}).get('state')=='not_created'
 and after.get('recording_control',{}).get('state')=='idle')
print(json.dumps(dict(before=before,responses=responses,after=after,file_state=original,
 recording_command_and_directories_unchanged=unchanged,passed=passed,
 human_eeg_recorded=False,screen_stimulus_started=False)))
'''


def main():
    client = connect()
    try:
        result = json.loads(command(client,
            '/usr/local/share/pynq-venv/bin/python3 -c '+shlex.quote(PROBE)))
    finally:
        client.close()
    with OUT.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=result['passed'], unchanged=result[
        'recording_command_and_directories_unchanged']), ensure_ascii=False))
    if not result['passed']:
        raise RuntimeError('No-data refusal check failed; inspect evidence')


if __name__ == '__main__':
    main()
