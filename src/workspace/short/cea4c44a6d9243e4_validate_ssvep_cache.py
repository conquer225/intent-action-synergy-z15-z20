"""Cache experiment: isolate production, test math first, then full-loop replay."""
import hashlib
import json
from pathlib import Path
import sys
import shutil

import numpy as np
from run_soak_stage import connect, PROD
from run_ssvep_causal_board_replay import command

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'eeg_apps_z15/output/ssvep_cache_20260927'
PREFIX='OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python3 '
CACHE={'ssvep_core.py':ROOT/'eeg_apps_z15/ssvep_core.py',
       'ssvep_stream.py':ROOT/'eeg_apps_z15/ssvep_stream.py',
       'cyton_sqi.py':ROOT/'pynq_guardianloop/cyton_sqi.py',
       'ssvep_shadow.py':ROOT/'pynq_guardianloop/ssvep_shadow.py'}


def save(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2),encoding='utf-8')


def compare_events(a,b):
    assert len(a)==len(b)
    maximum=0.
    for x,y in zip(a,b):
        for k in ('state','frequency_hz','target_index','window_start_index','window_end_index_exclusive','quality'):
            assert x.get(k)==y.get(k),k
        if x.get('scores') is not None:
            np.testing.assert_allclose(x['scores'],y['scores'],atol=1e-9,rtol=1e-7)
            maximum=max(maximum,float(np.max(np.abs(np.array(x['scores'])-y['scores']))))
    return dict(events=len(a),maximum_score_error=maximum,quality_exact=True,decisions_exact=True)


def stage():
    OUT.mkdir(exist_ok=True)
    if (OUT/'manifest.json').exists(): raise RuntimeError('Stage exists; resume explicitly')
    previous=json.loads((OUT.parent/'ssvep_async_20260927/manifest.json').read_text())
    c=connect(); c.get_transport().set_keepalive(15)
    try:
        remote=command(c,'mktemp -d /home/xilinx/ssvep-cache-XXXXXX').strip()
        assert remote.startswith('/home/xilinx/ssvep-cache-') and '\n' not in remote
        command(c,'mkdir '+remote+'/baseline '+remote+'/cached_sync '+remote+'/cached_async')
        original=OUT/'original'; original.mkdir()
        m=dict(stage=remote,protected={},candidate={},
            input_sha256=hashlib.sha256((OUT.parent/'board_pipeline_profile_20260926/input.npz').read_bytes()).hexdigest(),
            acceptance='Math: scores atol1e-9/rtol1e-7, decisions/quality exact; paced 22500 packets, primary exact, '
                'no errors/orphans, snapshot age p95<500ms/max<3s. Sync cache: total CPU reduces >=10%; '
                'async cache: packet p99 reduces >=20%, candidate input skips <1%. No changed thresholds.',
            bitstreams=command(c,'sha256sum '+PROD+'/guardianloop_pynq.bit '+PROD+'/guardianloop_pynq.hwh'))
        with c.open_sftp() as s:
            for name,h in previous['protected'].items():
                s.get(PROD+'/'+name,str(original/name))
                digest=hashlib.sha256((original/name).read_bytes()).hexdigest()
                assert digest==h,name
                m['protected'][name]=digest
                for folder in ('baseline','cached_sync','cached_async'):
                    s.put(str(original/name),remote+'/'+folder+'/'+name)
            for name,path in CACHE.items():
                m['candidate'][name]=hashlib.sha256(path.read_bytes()).hexdigest()
                for folder in ('cached_sync','cached_async'): s.put(str(path),remote+'/'+folder+'/'+name)
            for name in ('cyton_guardianloop.py','ssvep_async.py'):
                path=ROOT/'pynq_guardianloop'/name
                m['candidate'][name]=hashlib.sha256(path.read_bytes()).hexdigest()
                s.put(str(path),remote+'/cached_async/'+name)
            harnesses={n:ROOT/'pynq_guardianloop'/n for n in
                ('ssvep_shadow_replay.py','soak_service_replay.py','profile_service_replay.py',
                 'test_ssvep_shadow.py','test_ssvep_async.py','test_small_batch.py','test_seed_shadow.py',
                 'test_seed_quality_runtime.py','test_seed_shadow_web.py')}
            harnesses.update({n:ROOT/'eeg_apps_z15'/n for n in ('benchmark_ssvep_cache.py','test_ssvep_cache.py','test_ssvep_stream.py')})
            for folder in ('baseline','cached_sync','cached_async'):
                for name,path in harnesses.items(): s.put(str(path),remote+'/'+folder+'/'+name)
            s.put(str(OUT.parent/'board_pipeline_profile_20260926/input.npz'),remote+'/input.npz')
            raw=Path(json.loads((OUT.parent/'seed_recorded_replay_20260926/manifest.json').read_text())['source'])
            s.put(str(raw),remote+'/recorded.txt')
        save('manifest.json',m)
        tests=command(c,'cd '+remote+'/cached_async && '+PREFIX+'-m unittest test_ssvep_cache test_ssvep_stream test_ssvep_shadow test_ssvep_async test_small_batch test_seed_shadow test_seed_quality_runtime test_seed_shadow_web 2>&1',timeout=150)
        (OUT/'board_tests.txt').write_text(tests,encoding='utf-8'); print(tests,flush=True)
        log=command(c,'cd '+remote+'/cached_sync && '+PREFIX+'benchmark_ssvep_cache.py --baseline ../baseline --output kernels.json',timeout=90)
        print(log,flush=True)
        for folder in ('baseline','cached_sync'):
            print('Recorded bridge: '+folder,flush=True)
            command(c,'cd '+remote+'/'+folder+' && '+PREFIX+'ssvep_shadow_replay.py --input ../recorded.txt --output bridge',timeout=120)
            with c.open_sftp() as s:
                for n in ('events','report'):
                    suffix='bridge_report' if n=='report' else n
                    s.get(remote+'/'+folder+'/bridge/'+n+'.json',str(OUT/(folder+'_'+suffix+'.json')))
        with c.open_sftp() as s: s.get(remote+'/cached_sync/kernels.json',str(OUT/'kernels.json'))
        comparison=compare_events(json.loads((OUT/'baseline_events.json').read_text()),json.loads((OUT/'cached_sync_events.json').read_text()))
        save('math_parity.json',dict(passed=True,**comparison))
        print(comparison,flush=True)
    finally: c.close()


def paced():
    m=json.loads((OUT/'manifest.json').read_text())
    assert json.loads((OUT/'math_parity.json').read_text())['passed']
    c=connect(); c.get_transport().set_keepalive(15)
    try:
        for folder in ('baseline','cached_sync','cached_async'):
            print('Paced full loop '+folder,flush=True)
            command(c,'cd '+m['stage']+'/'+folder+' && '+PREFIX+'soak_service_replay.py --input ../input.npz --output paced --seconds 90',timeout=180)
            with c.open_sftp() as s:
                for n in ('report.json','monitor.jsonl','primary_results.json','ssvep.json','producer.json'):
                    s.get(m['stage']+'/'+folder+'/paced/'+n,str(OUT/(folder+'_'+n)))
            print((OUT/(folder+'_report.json')).read_text(),flush=True)
        assess(m,c)
    finally: c.close()


def assess(m,c):
    metrics={}
    for folder in ('baseline','cached_sync','cached_async'):
        report=json.loads((OUT/(folder+'_report.json')).read_text())
        rows=[json.loads(x) for x in (OUT/(folder+'_monitor.jsonl')).read_text().splitlines()]
        ages=[r['runtime']['input_age_at_snapshot_ms'] for r in rows if r.get('runtime')]
        metrics[folder]=dict(report=report,input_age_p95_ms=float(np.quantile(ages,.95)),
            input_age_max_ms=max(ages),total_cpu_s=report['parent_cpu_seconds']+report['children_cpu_seconds'],
            peak_sum_rss_kib=max(sum(p['rss_kib'] for p in [r['parent']]+r['children'] if p) for r in rows),
            final=json.loads((OUT/(folder+'_ssvep.json')).read_text()))
    checks={}
    for folder in ('cached_sync','cached_async'):
        v=metrics[folder]; base=metrics['baseline']; r=v['report']
        gate=dict(primary_parity=json.loads((OUT/(folder+'_primary_results.json')).read_text())==json.loads((OUT/'baseline_primary_results.json').read_text()),
            packets=r['packets_consumed']==22500 and r['packets_expected']==22500,
            clean_shutdown=not r['error'] and not r['monitor_errors'] and not r['remaining_children'],
            age=v['input_age_p95_ms']<500 and v['input_age_max_ms']<3000)
        if folder=='cached_sync': gate['cpu_reduction']=v['total_cpu_s']<.9*base['total_cpu_s']
        else:
            gate['packet_p99_improvement']=r['packet_compute_p99_ms']<.8*base['report']['packet_compute_p99_ms']
            gate['skips_bounded']=v['final']['skipped_ssvep_samples']+v['final']['worker_skipped_samples']<225
        checks[folder]=gate
    with c.open_sftp() as s:
        unchanged=all(hashlib.sha256(s.open(PROD+'/'+n).read()).hexdigest()==h for n,h in m['protected'].items())
    result=dict(metrics=metrics,checks=checks,production_unchanged=unchanged,
                passed={k:all(v.values()) and unchanged for k,v in checks.items()},acceptance=m['acceptance'])
    save('audit.json',result); print(json.dumps(result,indent=2),flush=True)


def primary_check(folder):
    m=json.loads((OUT/'manifest.json').read_text())
    assert folder in ('cached_sync','cached_async')
    assert json.loads((OUT/'audit.json').read_text())['passed'][folder]
    c=connect(); c.get_transport().set_keepalive(15)
    try:
        log=command(c,'cd '+m['stage']+'/'+folder+' && '+PREFIX+
                    'profile_service_replay.py --input ../input.npz --output primary_parity --repeats 1',timeout=300)
        (OUT/(folder+'_primary_profile.log')).write_text(log,encoding='utf-8')
        parity={}
        with c.open_sftp() as s:
            s.get(m['stage']+'/'+folder+'/primary_parity/report.json',str(OUT/(folder+'_primary_profile.json')))
            for case in ('recorded','synthetic'):
                path=OUT/(folder+'_primary_'+case+'.json')
                s.get(m['stage']+'/'+folder+'/primary_parity/'+case+'_0/primary_results.json',str(path))
                ref=OUT.parent/'ssvep_shadow_20260927'/('candidate_'+case+'_primary.json')
                parity[case]=json.loads(path.read_text())==json.loads(ref.read_text())
        save(folder+'_primary_parity.json',dict(passed=all(parity.values()),parity=parity,
            scope='Accelerated recorded81.128s/synthetic180s input: numerical parity only, not asynchronous timing.'))
        assert all(parity.values())
        print(parity,flush=True)
    finally: c.close()


def compact_ring_check():
    m=json.loads((OUT/'manifest.json').read_text())
    archive=OUT/'matrix_before_ring'; archive.mkdir()
    for path in OUT.iterdir():
        if path.is_file(): shutil.copy2(path,archive/path.name)
    c=connect(); c.get_transport().set_keepalive(15)
    try:
        folder=m['stage']+'/cached_sync'
        with c.open_sftp() as s:
            s.get(folder+'/ssvep_shadow.py',str(archive/'ssvep_shadow.py'))
            path=CACHE['ssvep_shadow.py']
            s.put(str(path),folder+'/ssvep_shadow.py')
            m['candidate']['ssvep_shadow.py']=hashlib.sha256(path.read_bytes()).hexdigest()
        m['refinement']='Only cached_sync uses two-column raw ring and removes unreachable rail history. cached_async remains archived matrix version.'
        save('manifest.json',m)
        tests=command(c,'cd '+folder+' && '+PREFIX+'-m unittest test_ssvep_cache test_ssvep_stream test_ssvep_shadow 2>&1',timeout=90)
        (OUT/'ring_tests.txt').write_text(tests,encoding='utf-8'); print(tests,flush=True)
        command(c,'cd '+folder+' && '+PREFIX+'ssvep_shadow_replay.py --input ../recorded.txt --output bridge_ring',timeout=120)
        with c.open_sftp() as s:
            for name in ('events','report'):
                suffix='bridge_report' if name=='report' else name
                s.get(folder+'/bridge_ring/'+name+'.json',str(OUT/('cached_sync_'+suffix+'.json')))
        parity=compare_events(json.loads((OUT/'baseline_events.json').read_text()),json.loads((OUT/'cached_sync_events.json').read_text()))
        save('math_parity.json',dict(passed=True,**parity)); print(parity,flush=True)
        command(c,'cd '+folder+' && '+PREFIX+'soak_service_replay.py --input ../input.npz --output paced_ring --seconds 90',timeout=180)
        with c.open_sftp() as s:
            for name in ('report.json','monitor.jsonl','primary_results.json','ssvep.json','producer.json'):
                s.get(folder+'/paced_ring/'+name,str(OUT/('cached_sync_'+name)))
        assess(m,c)
    finally: c.close()


if __name__=='__main__':
    if '--ring-check' in sys.argv: compact_ring_check()
    elif '--primary-check' in sys.argv: primary_check(sys.argv[-1])
    elif '--paced' in sys.argv: paced()
    else: stage()
