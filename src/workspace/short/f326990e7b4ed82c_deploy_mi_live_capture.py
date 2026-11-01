"""Verify bounded MI capture then update only the user-approved live sandbox."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import time

from deploy_mi_live_virtual import protect, FORMAL
from run_soak_stage import connect
from run_ssvep_backlog_replay import checked

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT/'eeg_apps_z15/output/mi_live_capture_20261003'
ASSETS = OUT/'runtime'
LIVE = '/home/xilinx/mi-live-virtual-20261003-a1'
CHECK = '/home/xilinx/mi-live-capture-check-20261003-a1'
PYTHON = '/usr/local/share/pynq-venv/bin/python3'
MODIFIED = ('mi_cued.py','mi_acquisition.py','mi_live_acquisition.py')
ADDED = ('mi_live_capture.py',)
TESTS = ('test_mi_cued','test_mi_virtual','test_mi_formal_entry',
         'test_mi_acquisition','test_mi_reader_tap','test_mi_live_capture')


def sha(data): return hashlib.sha256(data).hexdigest()


def read_json(sftp, path):
    with sftp.open(path,'rb') as stream: return json.loads(stream.read())


def save(name, value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def live_status(client):
    code="import json,urllib.request; print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:9104/api/mi-cue',timeout=2))))"
    return json.loads(checked(client,'timeout 5s python3 -c '+shlex.quote(code)))


def restore_files(client):
    checked(client,'systemctl stop guardianloop-cyton.service',sudo=True)
    for name in (*MODIFIED,'release_manifest.json'):
        checked(client,'install -m 644 '+CHECK+'/'+name+'.original '+LIVE+'/'+name,sudo=True)
    checked(client,'systemctl start guardianloop-cyton.service',sudo=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deploy',action='store_true')
    parser.add_argument('--restore',action='store_true')
    args=parser.parse_args()
    if args.deploy and args.restore: parser.error('Choose deploy or restore')
    client=connect()
    changed=False
    try:
        with client.open_sftp() as sftp:
            release=read_json(sftp,FORMAL+'/release_manifest.json')
            before=protect(client,sftp,release)
            if args.restore:
                deployment=json.loads((OUT/'DEPLOYMENT.json').read_text())
                for name in (*MODIFIED,*ADDED,'release_manifest.json'):
                    with sftp.open(LIVE+'/'+name,'rb') as stream:
                        if sha(stream.read()) != deployment['installed_sha256'][name]:
                            raise RuntimeError('Changed sandbox file; refusing overwrite: '+name)
                restore_files(client)
                if protect(client,sftp,release)!=before: raise RuntimeError('Protected files changed')
                print('Restored the pre-capture live sandbox; recordings and added inactive module preserved')
                return
            previous=read_json(sftp,LIVE+'/release_manifest.json')
            originals={}
            checked(client,'test ! -e '+CHECK+' && mkdir '+CHECK)
            for name,expected in previous['files'].items():
                with sftp.open(LIVE+'/'+name,'rb') as stream: data=stream.read()
                if sha(data)!=expected: raise RuntimeError('Sandbox manifest mismatch: '+name)
                with sftp.open(CHECK+'/'+name,'wb') as stream: stream.write(data)
                if name in MODIFIED: originals[name]=data
            with sftp.open(LIVE+'/release_manifest.json','rb') as stream:
                originals['release_manifest.json']=stream.read()
            if set(originals)!=set((*MODIFIED,'release_manifest.json')):
                raise RuntimeError('Missing backup source')
            for name in (*MODIFIED,*ADDED,'test_mi_live_capture.py','mi_reader_tap_smoke.py'):
                sftp.put(str(ASSETS/name),CHECK+'/'+name)
            for name in TESTS[:-1]:
                sftp.put(str(ROOT/'pynq_guardianloop'/(name+'.py')),CHECK+'/'+name+'.py')
            env='env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH='+CHECK+' '
            prefix='cd '+CHECK+' && '+env+PYTHON+' '
            print('ARM isolated capture regression; no service/USB/PL changes',flush=True)
            log=checked(client,'timeout 60s sh -c '+shlex.quote(prefix+'-m unittest '+' '.join(TESTS)))
            (OUT/'arm_capture_tests.log').write_text(log,encoding='utf-8')
            smoke_prefix='cd '+CHECK+' && '+env+'GUARDIANLOOP_MI_CAPTURE_DIR='+CHECK+'/synthetic-captures '+PYTHON+' '
            smoke_log=checked(client,'timeout 35s sh -c '+shlex.quote(smoke_prefix+
                'mi_reader_tap_smoke.py --model experimental_eegnet.npz --output capture-smoke.json'))
            (OUT/'arm_capture_smoke.log').write_text(smoke_log,encoding='utf-8')
            smoke=read_json(sftp,CHECK+'/capture-smoke.json')
            if not all(smoke.get(k) for k in ('passed','capture_complete','capture_original_adc_exact',
                                             'capture_input_exact','capture_normalization_exact')):
                raise RuntimeError('Capture smoke evidence failed')
            if protect(client,sftp,release)!=before: raise RuntimeError('Formal files changed during tests')
            save('VERIFICATION.json',dict(arm_tests_passed=True,smoke=smoke,before=before,deployed=False))
            if not args.deploy:
                print(json.dumps(smoke));return
            recording=read_json(sftp,'/run/guardianloop/recording_status.json')
            if recording.get('state')=='recording': raise RuntimeError('An existing recording is active')
            for _ in range(15):
                if live_status(client).get('state') not in ('active','awaiting_presentation'): break
                time.sleep(1)
            else: raise RuntimeError('An MI cue is active; do not interrupt it')
            for name,data in originals.items():
                with sftp.open(LIVE+'/'+name,'rb') as stream:
                    if stream.read()!=data: raise RuntimeError('Sandbox changed during verification: '+name)
                with sftp.open(CHECK+'/'+name+'.original','wb') as stream: stream.write(data)
            candidate=dict(previous,mi_capture='bounded_250Hz_ADC_events_exact_model_input')
            candidate['files']=dict(previous['files'])
            installed={}
            for name in (*MODIFIED,*ADDED):
                installed[name]=sha((ASSETS/name).read_bytes())
                candidate['files'][name]=installed[name]
            manifest=json.dumps(candidate,ensure_ascii=False,indent=2).encode('utf-8')
            installed['release_manifest.json']=sha(manifest)
            with sftp.open(CHECK+'/release_manifest.json','wb') as stream: stream.write(manifest)
            save('INSTALL_PLAN.json',dict(installed_sha256=installed,backup=CHECK,
                formal_unchanged=True,model_unchanged=True,pl_action=False,
                authorization='User allowed temporary diagnostic capture and acquisition service restart'))
            print('Restarting only temporary Cyton acquisition; model/PL/boot files unchanged',flush=True)
            checked(client,'systemctl stop guardianloop-cyton.service',sudo=True)
            changed=True
            for name in (*MODIFIED,*ADDED,'release_manifest.json'):
                checked(client,'install -m 644 '+CHECK+'/'+name+' '+LIVE+'/'+name,sudo=True)
            checked(client,'systemctl start guardianloop-cyton.service',sudo=True)
            for _ in range(25):
                time.sleep(1)
                try: state=live_status(client)
                except RuntimeError: continue
                capture=state.get('capture',{})
                if (state.get('input_state')=='ready' and capture.get('packets_written',0)>=500
                        and capture.get('state')=='recording'): break
            else: raise RuntimeError('Capture did not establish a real ready stream')
            if (state['source']!='live' or state['control_enabled'] or state['production_eligible']
                    or state['channels']!=['F3','F4','C3','C4','T7','T8','O1','O2']):
                raise RuntimeError('Unexpected candidate identity')
            after=protect(client,sftp,release)
            if after!=before: raise RuntimeError('Formal protected state changed')
            save('DEPLOYMENT.json',dict(installed_sha256=installed,before=before,after=after,
                formal_unchanged=True,model_unchanged=True,pl_unchanged=True,
                state=state,backup=CHECK,smoke=smoke))
            print(json.dumps(dict(deployed=True,state=state,formal_unchanged=True)),flush=True)
    except BaseException:
        if changed:
            print('Rolling back sandbox files and restoring acquisition',flush=True)
            restore_files(client)
        raise
    finally:
        client.close()


if __name__=='__main__':main()
