"""Isolated board comparison; never opens USB or reprograms PL."""
import hashlib
import json
from pathlib import Path
import sys
import shutil

import numpy as np
from run_soak_stage import connect, PROD
from run_ssvep_causal_board_replay import command

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'eeg_apps_z15/output/ssvep_async_20260927'
CHANGED = ['cyton_guardianloop.py', 'ssvep_shadow.py']
NEW = ['ssvep_async.py']


def save(name, obj):
    (OUT/name).write_text(json.dumps(obj, indent=2), encoding='utf-8')


def main():
    OUT.mkdir(exist_ok=True)
    if (OUT/'manifest.json').exists():
        raise RuntimeError('Existing experiment; inspect before resuming')
    previous = json.loads((OUT.parent/'ssvep_shadow_20260927/manifest.json').read_text())
    names = sorted(set(previous['protected']) | set(previous['candidate']))
    c = connect(); c.get_transport().set_keepalive(15)
    try:
        stage = command(c, 'mktemp -d /home/xilinx/ssvep-async-XXXXXX').strip()
        assert stage.startswith('/home/xilinx/ssvep-async-') and '\n' not in stage
        command(c, 'mkdir '+stage+'/baseline '+stage+'/candidate')
        original = OUT/'original'; original.mkdir()
        m = dict(stage=stage, protected={}, candidate={}, changed=CHANGED, new=NEW,
            acceptance='Primary output exact parity; all replay packets consumed; no orphan/error; '
                'paced input-age p95<500ms and max<3s; acquisition packet compute p99 improves >=20%; '
                'SSVEP worker continues producing candidates/quality states with <1% candidate input skips after startup. '
                'Total ARM CPU (parent+children) reported, not assumed reduced.',
            scope='Same old recording, 90s repeated paced replay. Live services remain running. No USB/PL or labeled SSVEP claims.')
        m['bitstreams'] = command(c, 'sha256sum '+PROD+'/guardianloop_pynq.bit '+PROD+'/guardianloop_pynq.hwh')
        with c.open_sftp() as s:
            for name in names:
                s.get(PROD+'/'+name, str(original/name))
                m['protected'][name] = hashlib.sha256((original/name).read_bytes()).hexdigest()
                for folder in ('baseline','candidate'):
                    s.put(str(original/name), stage+'/'+folder+'/'+name)
            for name in CHANGED+NEW:
                path = ROOT/'pynq_guardianloop'/name
                s.put(str(path),stage+'/candidate/'+name)
                m['candidate'][name] = hashlib.sha256(path.read_bytes()).hexdigest()
            for folder in ('baseline','candidate'):
                for name in ('soak_service_replay.py','profile_service_replay.py'):
                    s.put(str(ROOT/'pynq_guardianloop'/name),stage+'/'+folder+'/'+name)
            for name in ('test_ssvep_async.py','test_ssvep_shadow.py','test_small_batch.py',
                         'test_seed_shadow.py','test_seed_quality_runtime.py','test_seed_shadow_web.py'):
                s.put(str(ROOT/'pynq_guardianloop'/name),stage+'/candidate/'+name)
            s.put(str(OUT.parent/'board_pipeline_profile_20260926/input.npz'),stage+'/input.npz')
        save('manifest.json', m)
        prefix = 'OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python3 '
        tests = command(c, 'cd '+stage+'/candidate && '+prefix+'-m unittest test_ssvep_async test_ssvep_shadow test_small_batch test_seed_shadow test_seed_quality_runtime test_seed_shadow_web 2>&1',timeout=150)
        (OUT/'board_tests.txt').write_text(tests,encoding='utf-8'); print(tests,flush=True)
        for folder in ('baseline','candidate'):
            print('Paced replay '+folder,flush=True)
            log = command(c,'cd '+stage+'/'+folder+' && '+prefix+'soak_service_replay.py --input ../input.npz --output paced --seconds 90',timeout=180)
            (OUT/(folder+'.log')).write_text(log,encoding='utf-8')
            with c.open_sftp() as s:
                for name in ('report.json','monitor.jsonl','primary_results.json','ssvep.json','producer.json'):
                    s.get(stage+'/'+folder+'/paced/'+name,str(OUT/(folder+'_'+name)))
            print((OUT/(folder+'_report.json')).read_text(),flush=True)
        audit(m, c)
    finally:
        c.close()


def audit(m, c):
    result = dict(scope=m['scope'], acceptance=m['acceptance'], metrics={})
    for folder in ('baseline','candidate'):
        r=json.loads((OUT/(folder+'_report.json')).read_text())
        rows=[json.loads(line) for line in (OUT/(folder+'_monitor.jsonl')).read_text().splitlines()]
        ages=[v['runtime']['input_age_at_snapshot_ms'] for v in rows if v.get('runtime')]
        states=[v['ssvep']['state'] for v in rows if v.get('ssvep')]
        final=json.loads((OUT/(folder+'_ssvep.json')).read_text())
        result['metrics'][folder]=dict(report=r, input_age_p95_ms=float(np.quantile(ages,.95)),
            input_age_max_ms=max(ages), total_cpu_s=r['parent_cpu_seconds']+r['children_cpu_seconds'],
            peak_sum_rss_kib=max(sum(p['rss_kib'] for p in [v['parent']]+v['children'] if p) for v in rows),
            ssvep_state_counts={state:states.count(state) for state in set(states)}, ssvep_final=final)
    a,b=result['metrics']['baseline'],result['metrics']['candidate']
    checks = dict(primary_parity=json.loads((OUT/'baseline_primary_results.json').read_text()) ==
                  json.loads((OUT/'candidate_primary_results.json').read_text()),
        packets_and_cleanup=all(v['report']['packets_consumed']==22500 and not v['report']['error']
            and not v['report']['monitor_errors'] and not v['report']['remaining_children'] for v in (a,b)),
        input_age=b['input_age_p95_ms']<500 and b['input_age_max_ms']<3000,
        packet_p99_improvement=b['report']['packet_compute_p99_ms']<.8*a['report']['packet_compute_p99_ms'],
        candidate_states=sum(b['ssvep_state_counts'].get(k,0) for k in ('candidate_only','signal_invalid'))>0,
        skips_bounded=(b['ssvep_final']['skipped_ssvep_samples']+b['ssvep_final']['worker_skipped_samples'])<225)
    with c.open_sftp() as s:
        checks['production_unchanged']=all(hashlib.sha256(s.open(PROD+'/'+n).read()).hexdigest()==h for n,h in m['protected'].items())
    result.update(checks=checks,passed=all(checks.values()))
    save('audit.json',result)
    print(json.dumps(result,indent=2),flush=True)


def retry(buffered=False, priority=False):
    m=json.loads((OUT/'manifest.json').read_text())
    attempt=OUT/('buffered_attempt' if priority else 'compact_attempt' if buffered else 'initial_attempt'); attempt.mkdir()
    replay_dir='paced_priority' if priority else 'paced_buffered' if buffered else 'paced_compact'
    for path in OUT.glob('candidate*'):
        if path.is_file(): shutil.copy2(path,attempt/path.name)
    for name in ('audit.json','manifest.json','board_tests.txt'):
        shutil.copy2(OUT/name,attempt/name)
    c=connect(); c.get_transport().set_keepalive(15)
    try:
        stage=m['stage']+'/candidate'
        with c.open_sftp() as s:
            s.put(str(ROOT/'pynq_guardianloop/test_ssvep_async.py'),stage+'/test_ssvep_async.py')
            for name in CHANGED+NEW:
                s.get(stage+'/'+name,str(attempt/name))
                path=ROOT/'pynq_guardianloop'/name
                s.put(str(path),stage+'/'+name)
                m['candidate'][name]=hashlib.sha256(path.read_bytes()).hexdigest()
        save('manifest.json',m)
        prefix='OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python3 '
        tests=command(c,'cd '+stage+' && '+prefix+'-m unittest test_ssvep_async test_ssvep_shadow 2>&1',timeout=120)
        (OUT/'final_tests.txt').write_text(tests,encoding='utf-8'); print(tests,flush=True)
        log=command(c,'cd '+stage+' && '+prefix+'soak_service_replay.py --input ../input.npz --output '+replay_dir+' --seconds 90',timeout=180)
        (OUT/'candidate.log').write_text(log,encoding='utf-8')
        with c.open_sftp() as s:
            for name in ('report.json','monitor.jsonl','primary_results.json','ssvep.json','producer.json'):
                s.get(stage+'/'+replay_dir+'/'+name,str(OUT/('candidate_'+name)))
        audit(m,c)
    finally:
        c.close()


def primary_check():
    """Accelerated replay is for primary numerical parity, not async throughput."""
    m=json.loads((OUT/'manifest.json').read_text())
    c=connect(); c.get_transport().set_keepalive(15)
    stage=m['stage']+'/candidate'
    try:
        with c.open_sftp() as s:
            s.put(str(ROOT/'pynq_guardianloop/test_ssvep_async.py'),stage+'/test_ssvep_async.py')
        prefix='OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python3 '
        tests=command(c,'cd '+stage+' && '+prefix+'-m unittest test_ssvep_async test_ssvep_shadow 2>&1',timeout=120)
        (OUT/'final_tests.txt').write_text(tests,encoding='utf-8'); print(tests,flush=True)
        log=command(c,'cd '+stage+' && '+prefix+'profile_service_replay.py --input ../input.npz --output primary_parity --repeats 1',timeout=300)
        (OUT/'primary_profile.log').write_text(log,encoding='utf-8')
        parity={}
        with c.open_sftp() as s:
            s.get(stage+'/primary_parity/report.json',str(OUT/'primary_profile.json'))
            for case in ('recorded','synthetic'):
                path=OUT/('primary_'+case+'.json')
                s.get(stage+'/primary_parity/'+case+'_0/primary_results.json',str(path))
                reference=OUT.parent/'ssvep_shadow_20260927'/('candidate_'+case+'_primary.json')
                parity[case]=json.loads(path.read_text())==json.loads(reference.read_text())
        save('primary_parity.json',dict(parity=parity,passed=all(parity.values()),
            scope='81.128s recorded +180s synthetic accelerated input; same-input primary outputs only. '
                  'Do not interpret deliberate faster-than-real-time SSVEP queue overflow as paced loss.'))
        print(parity,flush=True)
        assert all(parity.values())
    finally:
        c.close()


if __name__=='__main__':
    if '--priority-check' in sys.argv:
        retry(priority=True)
    elif '--primary-check' in sys.argv:
        primary_check()
    elif '--buffered-check' in sys.argv:
        retry(buffered=True)
    elif '--retry' in sys.argv:
        retry()
    elif '--audit' in sys.argv:
        client=connect()
        try: audit(json.loads((OUT/'manifest.json').read_text()),client)
        finally: client.close()
    else:
        main()
