"""Verify the installed software and cancel its rollback only after safe checks."""
import json
from pathlib import Path
import shlex

import run_live_system as helpers

OUT=Path(__file__).resolve().parent/'output/load_relief_20261007'


def main():
    state=json.loads((OUT/'deployment-state.json').read_text())
    code=r'''
import hashlib,json,pathlib,sys,time,subprocess
root=pathlib.Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
stage=pathlib.Path(sys.argv[1]);expected=sys.argv[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(root/'release_manifest.json')==expected
manifest=json.loads((root/'release_manifest.json').read_text())
assert all(sha(root/n)==h for n,h in manifest['files'].items())
record=json.loads((stage/'backup/installation.json').read_text())
assert record['phase']=='awaiting_live_check'
assert all(sha(pathlib.Path(item['target']))==item['new_sha'] for item in record['files'])
fields=subprocess.check_output(['/bin/systemctl','show','guardianloop-cyton','guardianloop-web','-p','Id','-p','MainPID','-p','ActiveState','-p','NRestarts'],text=True)
assert fields.count('ActiveState=active')==2
sys.path.insert(0,'/home/xilinx/brain_eye_coexist_20261005/eye/src')
from coexist_guard import CoexistGuard
from pynq import PL
pl=PL.bitfile_name
assert pl==str(root/'guardianloop_pynq.bit')
admission=CoexistGuard('/home/xilinx/brain_eye_coexist_20261005/eye',pl).verify()
seed=json.loads(pathlib.Path('/tmp/guardianloop-seed-shadow.json').read_text())
assert seed['valid'] is False and (seed.get('last_gap') or {}).get('reason')=='page_task_suspended'
assert seed['source']=='live'
sys.path.insert(0,'/home/xilinx/gl-media-20261007-314e8796')
sys.path.insert(0,'/home/xilinx/gl-media-20261007-314e8796/system_runtime')
from system_hdmi import UnifiedDisplay
before=time.monotonic()
display=UnifiedDisplay('/home/xilinx/brain_eye_coexist_20261005/eye',live=True,dimensions=(288,512),shell_cache='/home/xilinx/gl-media-20261007-314e8796/menu-shells-portrait-live.npz')
elapsed=time.monotonic()-before
status=json.loads(pathlib.Path('/run/guardianloop/status.json').read_text())
result=dict(release_id=manifest['release_id'],manifest_sha=expected,verified_files=len(manifest['files']),
 pl=pl,services=fields,admission=admission,seed_paused=True,shells=len(display.shells),
 cached_menu_constructor_ms=elapsed*1000,primary_state=status.get('state'),primary_valid=status.get('valid'),
 primary_reason=status.get('reason'),models_changed=False,physical_output_enabled=False,
 live_HDMI_acceptance=False)
subprocess.run(['/bin/systemctl','stop',record['timer']+'.timer'],check=True,timeout=10)
record['phase']='installed_verified_software_only'
(stage/'backup/installation.json').write_text(json.dumps(record,indent=2))
(stage/'verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
'''
    client=helpers.upload.trial.connect('192.168.2.99')
    try:
        report=helpers.execute(client,shlex.join(['env','XILINX_XRT=/usr',helpers.PYTHON,'-c',code,
                                                  state['stage'],state['manifest_sha']]),True)
        value=json.loads(report)
        (OUT/'installation-verification.json').write_text(json.dumps(value,indent=2))
        print(json.dumps(value,indent=2))
    finally:client.close()


if __name__=='__main__':main()
