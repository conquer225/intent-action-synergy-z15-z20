"""Board-side pipe-only reader fault and clean-recovery checks; no deployment."""
import hashlib
import json
from pathlib import Path
import sys

from run_soak_stage import connect, PROD
from run_ssvep_causal_board_replay import command
from validate_ssvep_cache import PREFIX, ROOT

OUT = ROOT/'eeg_apps_z15/output/reader_faults_final_20260927'
PREVIOUS = ROOT/'eeg_apps_z15/output/ssvep_cache_20260927'
CHANGED = ROOT/'pynq_guardianloop/cyton_guardianloop.py'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(name, value):
    (OUT/name).write_text(json.dumps(value,indent=2),encoding='utf-8')


def main():
    resume='--resume' in sys.argv
    if resume:
        if (OUT/'audit.json').exists():
            raise RuntimeError('Experiment completed; preserve it')
        manifest=json.loads((OUT/'manifest.json').read_text())
        stage=manifest['stage']
    else:
        OUT.mkdir(exist_ok=False)
    previous=json.loads((PREVIOUS/'manifest.json').read_text())
    c=connect()
    c.get_transport().set_keepalive(15)
    try:
        if not resume:
            stage=command(c,'mktemp -d /home/xilinx/reader-faults-XXXXXX').strip()
            if not stage.startswith('/home/xilinx/reader-faults-') or '\n' in stage:
                raise RuntimeError('Bad stage path')
            command(c,'mkdir '+stage+'/baseline '+stage+'/candidate')
            manifest=dict(stage=stage, protected=previous['protected'], candidate_sha256=digest(CHANGED.read_bytes()),
                services_before=command(c,'systemctl show guardianloop-cyton guardianloop-web -p Id -p ActiveState -p MainPID -p NRestarts'),
                scope='Isolated Linux pipe and replay fault injection. No USB, PL, service restart or production edit.')
        with c.open_sftp() as s:
            for n,h in previous['protected'].items():
                if digest(s.open(PROD+'/'+n).read())!=h:
                    raise RuntimeError('Production drift: '+n)
                baseline=PREVIOUS/'original'/n
                if digest(baseline.read_bytes())!=h:
                    raise RuntimeError('Original snapshot drift: '+n)
                if not resume:
                    s.put(str(baseline),stage+'/baseline/'+n)
                s.put(str(CHANGED if n=='cyton_guardianloop.py' else baseline),stage+'/candidate/'+n)
            for name in ('test_cyton_reader_faults.py','test_seed_reader_timing.py',
                         'test_small_batch.py','soak_service_replay.py'):
                path=ROOT/'pynq_guardianloop'/name
                s.put(str(path),stage+'/candidate/'+name)
            if not resume:
                s.put(str(ROOT/'pynq_guardianloop/soak_service_replay.py'),stage+'/baseline/soak_service_replay.py')
            input_path=PREVIOUS.parent/'board_pipeline_profile_20260926/input.npz'
            if digest(input_path.read_bytes())!=previous['input_sha256']:
                raise RuntimeError('Replay input drift')
            if not resume:
                s.put(str(input_path),stage+'/input.npz')
        if not resume:
            save('manifest.json',manifest)
        else:
            save('resume_candidate.json',dict(candidate_sha256=digest(CHANGED.read_bytes()),
                test_sha256=digest((ROOT/'pynq_guardianloop/test_cyton_reader_faults.py').read_bytes()),
                reason='Closed FD was reused by a child pipe; deterministic injected EIO replaces that test.'))
        tests=command(c,'cd '+stage+'/candidate && '+PREFIX+
            '-m unittest test_cyton_reader_faults test_seed_reader_timing test_small_batch 2>&1',timeout=90)
        (OUT/'unit_tests.txt').write_text(tests,encoding='utf-8')
        print(tests,flush=True)
        # A normal replay of the same input must retain primary behavior.
        for variant in ('baseline','candidate'):
            if (OUT/(variant+'_report.json')).exists():
                continue
            print('Healthy '+variant,flush=True)
            output='healthy_repaired' if resume and variant=='candidate' else 'healthy'
            command(c,'cd '+stage+'/'+variant+' && '+PREFIX+
                'soak_service_replay.py --input ../input.npz --seconds 20 --output '+output,timeout=90)
            with c.open_sftp() as s:
                for name in ('report.json','primary_results.json','status.json','ssvep.json'):
                    s.get(stage+'/'+variant+'/'+output+'/'+name,str(OUT/(variant+'_'+name)))
        baseline=json.loads((OUT/'baseline_primary_results.json').read_text())
        candidate=json.loads((OUT/'candidate_primary_results.json').read_text())
        healthy_exact=baseline==candidate
        print('healthy primary exact='+str(healthy_exact),flush=True)
        fault_results={}
        for kind in ('serial_io_error','queue_full','serial_eof'):
            # Expected process failure, with safe INVALID status and a structured diagnostic.
            cmd=('cd '+stage+'/candidate && '+PREFIX+
                'soak_service_replay.py --input ../input.npz --seconds 20 --output fault_'+kind+
                ' --reader-fault-after 750 --reader-fault-kind '+kind)
            _,stdout,stderr=c.exec_command(cmd,timeout=60)
            log=stdout.read().decode()+stderr.read().decode()
            code=stdout.channel.recv_exit_status()
            (OUT/(kind+'.log')).write_text(log,encoding='utf-8')
            if code==0:
                raise RuntimeError('Fault did not fail: '+kind)
            with c.open_sftp() as s:
                for name in ('report.json','status.json','ssvep.json','offline-replay.log'):
                    s.get(stage+'/candidate/fault_'+kind+'/'+name,
                          str(OUT/(kind+'_'+name.replace('.','_'))))
            status=json.loads((OUT/(kind+'_status_json')).read_text())
            report=json.loads((OUT/(kind+'_report_json')).read_text())
            fault_results[kind]=dict(exit_code=code,status_reason=status.get('reason'),
                status_valid=status.get('valid'),error=report.get('error'),
                remaining_children=report.get('remaining_children'),
                logged_diagnostic='CYTON_READER_FAILURE:' in log)
            print(kind+' '+json.dumps(fault_results[kind]),flush=True)
        with c.open_sftp() as s:
            unchanged=all(digest(s.open(PROD+'/'+n).read())==h
                          for n,h in previous['protected'].items())
        services=command(c,'systemctl show guardianloop-cyton guardianloop-web -p Id -p ActiveState -p MainPID -p NRestarts')
        passing=(healthy_exact and unchanged and all(
            x['exit_code']!=0 and x['status_reason']=='READER_'+kind.upper()
            and x['status_valid'] is False and not x['remaining_children']
            and x['logged_diagnostic'] for kind,x in fault_results.items()))
        save('audit.json',dict(passed=passing,healthy_primary_exact=healthy_exact,
            faults=fault_results,production_unchanged=unchanged,
            services_after=services,deployed=False))
        print('passed='+str(passing),flush=True)
        if not passing:
            raise RuntimeError('Reader-fault acceptance failed; see audit.json')
    finally:
        c.close()


if __name__=='__main__':
    main()
