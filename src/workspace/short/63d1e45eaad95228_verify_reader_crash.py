"""Regression for an unreported child exit; stage separate from prior audit."""
import hashlib
import json
from pathlib import Path
import sys

from run_soak_stage import connect, PROD
from run_ssvep_causal_board_replay import command
from validate_ssvep_cache import ROOT, PREFIX

OUT=ROOT/'eeg_apps_z15/output/reader_crash_final_20260927'
PRIOR=ROOT/'eeg_apps_z15/output/reader_faults_final_20260927'
ENTRY=ROOT/'pynq_guardianloop/cyton_guardianloop.py'
TEST=ROOT/'pynq_guardianloop/test_cyton_reader_faults.py'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2),encoding='utf-8')


def main():
    resume='--resume' in sys.argv
    if resume:
        if (OUT/'audit.json').exists():
            raise RuntimeError('Experiment already completed')
        stage=json.loads((OUT/'manifest.json').read_text())['stage']
    else:
        OUT.mkdir(exist_ok=False)
    prior=json.loads((PRIOR/'deployment.json').read_text())
    old=json.loads((PRIOR/'manifest.json').read_text())
    if prior['phase']!='verified':
        raise RuntimeError('Earlier promotion is not verified')
    c=connect()
    try:
        if not resume:
            stage=command(c,'mktemp -d /home/xilinx/reader-crash-XXXXXX').strip()
            if not stage.startswith('/home/xilinx/reader-crash-') or '\n' in stage:
                raise RuntimeError('Invalid stage path')
        with c.open_sftp() as s:
            for name,digest in old['protected'].items():
                expected=prior['installed_sha256'] if name=='cyton_guardianloop.py' else digest
                if sha(s.open(PROD+'/'+name).read())!=expected:
                    raise RuntimeError('Production drift: '+name)
        if not resume:
            command(c,'cp -a '+old['stage']+'/candidate '+stage+'/candidate')
        with c.open_sftp() as s:
            s.put(str(ENTRY),stage+'/candidate/cyton_guardianloop.py')
            s.put(str(TEST),stage+'/candidate/test_cyton_reader_faults.py')
        manifest=dict(stage=stage,entry_sha256=sha(ENTRY.read_bytes()),
            previous_installed_sha256=prior['installed_sha256'],
            protected=old['protected'],
            services_before=command(c,'systemctl show guardianloop-cyton guardianloop-web -p Id -p ActiveState -p MainPID -p NRestarts'),
            scope='Isolated new child-crash regression; no USB/PL use or production write.')
        if not resume:
            save('manifest.json',manifest)
        tests=command(c,'cd '+stage+'/candidate && '+PREFIX+
            '-m unittest test_cyton_reader_faults test_seed_reader_timing test_small_batch 2>&1',timeout=90)
        (OUT/'tests.txt').write_text(tests,encoding='utf-8')
        print(tests,flush=True)
        command(c,'cd '+stage+'/candidate && '+PREFIX+
            'soak_service_replay.py --input '+old['stage']+'/input.npz --seconds 20 --output healthy_crash',timeout=90)
        with c.open_sftp() as s:
            for n in ('report.json','primary_results.json'):
                s.get(stage+'/candidate/healthy_crash/'+n,str(OUT/n))
            unchanged=all(sha(s.open(PROD+'/'+n).read())==
                (prior['installed_sha256'] if n=='cyton_guardianloop.py' else h)
                for n,h in old['protected'].items())
        reference=json.loads((PRIOR/'candidate_primary_results.json').read_text())
        parity=json.loads((OUT/'primary_results.json').read_text())==reference
        report=json.loads((OUT/'report.json').read_text())
        passed=parity and unchanged and report['packets_consumed']==5000 and not report['error']
        save('audit.json',dict(passed=passed,healthy_primary_exact=parity,
            production_unchanged=unchanged,packet_count=report['packets_consumed'],deployed=False))
        print('passed='+str(passed),flush=True)
        if not passed:
            raise RuntimeError('Crash regression acceptance failed')
    finally:
        c.close()


if __name__=='__main__':
    main()
