"""Stage packet-bridge tests and old-recording/full-loop replay off production."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np

from run_ssvep_causal_board_replay import command
from run_soak_stage import connect, PROD

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'eeg_apps_z15/output/ssvep_shadow_20260927'
NEW = ['ssvep_shadow.py', 'ssvep_core.py', 'ssvep_stream.py',
       'ssvep_causal_protocol.json', 'ssvep_candidate_sos.npy']
CHANGED = ['cyton_guardianloop.py', 'guardianloop_web.py']


def sources():
    paths = {n: ROOT/'pynq_guardianloop'/n for n in CHANGED+['ssvep_shadow.py']}
    paths.update({n: ROOT/'eeg_apps_z15'/n for n in
                  ['ssvep_core.py','ssvep_stream.py','ssvep_causal_protocol.json']})
    paths['ssvep_candidate_sos.npy'] = ROOT/'eeg_apps_z15/output/ssvep_causal_20260926/candidate_sos.npy'
    return paths


def compare_recorded_bridge():
    sys.path.insert(0, str(ROOT/'pynq_guardianloop'))
    from ssvep_shadow import SSVEPShadow, CHANNELS
    raw = Path(json.loads((ROOT/'eeg_apps_z15/output/seed_recorded_replay_20260926/manifest.json').read_text())['source'])
    rows = np.loadtxt(raw, delimiter=',', skiprows=5, usecols=range(9))
    shadow = SSVEPShadow(sources()['ssvep_causal_protocol.json'], sources()['ssvep_candidate_sos.npy'],
                        CHANNELS, source='replay', status_path=OUT/'pc_status.json')
    expected = []
    for i,row in enumerate(rows):
        expected.extend(shadow.packet(row[1:9], int(row[0]), now=i/250,
                                      adc_rails=np.abs(row[7:9]) >= 187500*.99))
    actual = json.loads((OUT/'replay_events.json').read_text())
    assert len(expected) == len(actual)
    maximum = 0.
    for a,b in zip(expected,actual):
        for key in ('state','frequency_hz','target_index','window_start_index','window_end_index_exclusive','control_enabled'):
            assert a.get(key) == b.get(key), key
        assert a['quality']['hard_bad'] == b['quality']['hard_bad']
        assert a['quality']['warning'] == b['quality']['warning']
        if a['scores'] is not None:
            np.testing.assert_allclose(a['scores'],b['scores'],atol=1e-6,rtol=1e-7)
            maximum = max(maximum, float(np.max(np.abs(np.asarray(a['scores'])-b['scores']))))
    return dict(passed=True, events=len(actual), maximum_score_error=maximum)


def paced_check():
    manifest = json.loads((OUT/'manifest.json').read_text())
    audit = json.loads((OUT/'audit.json').read_text())
    assert audit['passed']
    client = connect()
    client.get_transport().set_keepalive(15)
    stage = manifest['stage']+'/candidate'
    try:
        with client.open_sftp() as sftp:
            sftp.put(str(ROOT/'pynq_guardianloop/soak_service_replay.py'), stage+'/soak_service_replay.py')
        log = command(client, 'cd '+stage+' && OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 XILINX_XRT=/usr '
                      '/usr/local/share/pynq-venv/bin/python3 soak_service_replay.py --input ../input.npz --output paced --seconds 90',timeout=180)
        (OUT/'paced.log').write_text(log,encoding='utf-8')
        with client.open_sftp() as sftp:
            for name in ('report.json','monitor.jsonl','ssvep.json','offline-replay.log'):
                sftp.get(stage+'/paced/'+name,str(OUT/('paced_'+name)))
        report = json.loads((OUT/'paced_report.json').read_text())
        rows = [json.loads(line) for line in (OUT/'paced_monitor.jsonl').read_text().splitlines()]
        lags = [r['runtime']['input_age_at_snapshot_ms'] for r in rows
                if r.get('runtime') and 'input_age_at_snapshot_ms' in r['runtime']]
        assert report['packets_consumed']==report['packets_expected']==22500
        assert report['error'] is None and not report['monitor_errors'] and not report['remaining_children']
        assert lags and np.quantile(lags,.95)<500 and max(lags)<3000
        audit['paced_check'] = dict(passed=True, packets=22500, input_age_p95_ms=float(np.quantile(lags,.95)),
                                   input_age_max_ms=max(lags), report=report)
        audit['recorded_bridge_pc_arm'] = compare_recorded_bridge()
        (OUT/'audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
        print(json.dumps(audit['paced_check'],indent=2))
    finally:
        client.close()


def optimized_check(final=False):
    """Retain the first attempt, then check the one-call SQI optimization."""
    manifest = json.loads((OUT/'manifest.json').read_text())
    archive = 'combined_' if final else 'initial_'
    replay_dir = 'replay_final' if final else 'replay_combined'
    profile_dir = 'profile_final' if final else 'profile_combined'
    if (OUT/(archive+'manifest.json')).exists():
        raise RuntimeError('Optimization already staged; inspect its outputs')
    for name in ('manifest.json','candidate_profile.json','candidate_profile.log',
                 'replay_report.json','replay_events.json','replay_status.json'):
        shutil.copy2(OUT/name, OUT/(archive+name))
    client = connect(); client.get_transport().set_keepalive(15)
    stage = manifest['stage']+'/candidate'
    try:
        with client.open_sftp() as sftp:
            sftp.get(stage+'/ssvep_shadow.py',str(OUT/(archive+'ssvep_shadow.py')))
            source = sources()['ssvep_shadow.py']
            sftp.put(str(source),stage+'/ssvep_shadow.py')
            sftp.put(str(ROOT/'pynq_guardianloop/test_ssvep_shadow.py'),stage+'/test_ssvep_shadow.py')
            manifest['candidate']['ssvep_shadow.py'] = hashlib.sha256(source.read_bytes()).hexdigest()
        (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        prefix = 'OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python3 '
        tests = command(client,'cd '+stage+' && '+prefix+'-m unittest test_ssvep_shadow 2>&1',timeout=90)
        (OUT/('final_tests.txt' if final else 'optimized_tests.txt')).write_text(tests,encoding='utf-8'); print(tests,flush=True)
        print(command(client,'cd '+stage+' && '+prefix+'ssvep_shadow_replay.py --input ../recorded.txt --output '+replay_dir,timeout=120),flush=True)
        print('Rechecking optimized complete main loop',flush=True)
        log = command(client,'cd '+stage+' && '+prefix+'profile_service_replay.py --input ../input.npz --output '+profile_dir+' --repeats 1',timeout=300)
        (OUT/'candidate_profile.log').write_text(log,encoding='utf-8')
        with client.open_sftp() as sftp:
            for name in ('report','events','status'):
                sftp.get(stage+'/'+replay_dir+'/'+name+'.json',str(OUT/('replay_'+name+'.json')))
            sftp.get(stage+'/'+profile_dir+'/report.json',str(OUT/'candidate_profile.json'))
            for case in ('recorded','synthetic'):
                sftp.get(stage+'/'+profile_dir+'/'+case+'_0/primary_results.json',str(OUT/('candidate_'+case+'_primary.json')))
        audit = dict(parity={},recorded_bridge_pc_arm=compare_recorded_bridge(),
                     initial_check='200ms terminal backlog gate failed; baseline synthetic ended at 450.9ms vs initial candidate 446.6ms. Initial artifacts retained. This is a final heavy window, not evidence of growing backlog.',
                     acceptance='Exact primary output parity, wall compute <80% of record duration; final simulated backlog <3s. Also require real paced reader replay p95 input age <500ms, max <3s before deployment.',
                     timing=[],scope='Engineering replay only; no accuracy or hard-real-time claim')
        for case in ('recorded','synthetic'):
            a=json.loads((OUT/('baseline_'+case+'_primary.json')).read_text())
            b=json.loads((OUT/('candidate_'+case+'_primary.json')).read_text())
            audit['parity'][case]=a==b
        assert all(audit['parity'].values())
        baseline=json.loads((OUT/'baseline_profile.json').read_text())['runs']
        candidate=json.loads((OUT/'candidate_profile.json').read_text())['runs']
        for a,b in zip(baseline,candidate):
            assert a['case']==b['case']
            audit['timing'].append(dict(case=b['case'],baseline_wall_s=a['wall_s'],candidate_wall_s=b['wall_s'],
                                       input_seconds=b['input_seconds'],max_simulated_backlog_ms=b['simulated_queue_delay_max_ms'],
                                       final_simulated_backlog_ms=b['simulated_queue_delay_final_ms']))
            assert b['wall_s'] < .8*b['input_seconds']
            assert b['simulated_queue_delay_final_ms'] < 3000
        with client.open_sftp() as sftp:
            audit['protected_unchanged']=all(hashlib.sha256(sftp.open(PROD+'/'+n).read()).hexdigest()==h
                                              for n,h in manifest['protected'].items())
        assert audit['protected_unchanged']
        audit['passed']=True
        (OUT/'audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
        print(json.dumps(audit,indent=2),flush=True)
    finally:
        client.close()


def main():
    OUT.mkdir(exist_ok=True)
    if (OUT/'manifest.json').exists():
        raise RuntimeError('Existing stage; inspect/resume its outputs rather than relaunch')
    client = connect()
    client.get_transport().set_keepalive(15)
    try:
        stage = command(client, 'mktemp -d /home/xilinx/ssvep-shadow-XXXXXX')
        assert stage.startswith('/home/xilinx/ssvep-shadow-') and '\n' not in stage
        command(client, 'mkdir '+stage+'/baseline '+stage+'/candidate')
        original = OUT/'original'; original.mkdir(exist_ok=True)
        names = list(json.loads((ROOT/'eeg_apps_z15/output/runtime_soak_20260926/manifest.json').read_text())['protected'])
        manifest = dict(stage=stage, protected={}, candidate={}, changed=CHANGED, new=NEW)
        manifest['bitstreams'] = command(client, 'sha256sum '+PROD+'/guardianloop_pynq.bit '+PROD+'/guardianloop_pynq.hwh')
        with client.open_sftp() as sftp:
            for name in names:
                sftp.get(PROD+'/'+name, str(original/name))
                manifest['protected'][name] = hashlib.sha256((original/name).read_bytes()).hexdigest()
                for folder in ('baseline', 'candidate'):
                    sftp.put(str(original/name), stage+'/'+folder+'/'+name)
            for name, source in sources().items():
                destination = stage+'/candidate/'+name
                sftp.put(str(source), destination)
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                assert command(client, 'sha256sum '+destination).split()[0] == digest
                manifest['candidate'][name] = digest
            for name in ['test_ssvep_shadow.py','ssvep_shadow_replay.py','test_seed_shadow_web.py',
                         'test_seed_shadow.py','test_seed_quality_runtime.py','test_small_batch.py']:
                sftp.put(str(ROOT/'pynq_guardianloop'/name),stage+'/candidate/'+name)
            for folder in ('baseline','candidate'):
                sftp.put(str(ROOT/'pynq_guardianloop/profile_service_replay.py'),stage+'/'+folder+'/profile_service_replay.py')
            raw = Path(json.loads((ROOT/'eeg_apps_z15/output/seed_recorded_replay_20260926/manifest.json').read_text())['source'])
            sftp.put(str(raw),stage+'/recorded.txt')
            sftp.put(str(ROOT/'eeg_apps_z15/output/board_pipeline_profile_20260926/input.npz'),stage+'/input.npz')
        manifest['recorded_sha256'] = hashlib.sha256(raw.read_bytes()).hexdigest()
        (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        prefix = 'OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python3 '
        tests = command(client, 'cd '+stage+'/candidate && '+prefix+'-m unittest test_ssvep_shadow test_seed_shadow_web test_seed_shadow test_seed_quality_runtime test_small_batch 2>&1', timeout=120)
        (OUT/'board_tests.txt').write_text(tests,encoding='utf-8'); print(tests,flush=True)
        replay = command(client, 'cd '+stage+'/candidate && '+prefix+'ssvep_shadow_replay.py --input ../recorded.txt --output replay',timeout=180)
        print(replay,flush=True)
        for folder in ('baseline','candidate'):
            print('Running isolated full main loop: '+folder,flush=True)
            log = command(client, 'cd '+stage+'/'+folder+' && '+prefix+'profile_service_replay.py --input ../input.npz --output profile --repeats 1',timeout=240)
            (OUT/(folder+'_profile.log')).write_text(log,encoding='utf-8')
        with client.open_sftp() as sftp:
            for remote, local in [('candidate/replay/report.json','replay_report.json'),
                                  ('candidate/replay/events.json','replay_events.json'),
                                  ('candidate/replay/status.json','replay_status.json')]:
                sftp.get(stage+'/'+remote,str(OUT/local))
            for folder in ('baseline','candidate'):
                sftp.get(stage+'/'+folder+'/profile/report.json',str(OUT/(folder+'_profile.json')))
                for case in ('recorded','synthetic'):
                    sftp.get(stage+'/'+folder+'/profile/'+case+'_0/primary_results.json',str(OUT/(folder+'_'+case+'_primary.json')))
        audit = {'parity':{}, 'recorded_bridge_pc_arm':compare_recorded_bridge(),
                 'scope':'Recorded/synthetic packet replay; UART and PL bypassed; no human accuracy claim'}
        for case in ('recorded','synthetic'):
            a = json.loads((OUT/('baseline_'+case+'_primary.json')).read_text())
            b = json.loads((OUT/('candidate_'+case+'_primary.json')).read_text())
            audit['parity'][case] = a == b
        assert all(audit['parity'].values()), 'Primary outputs changed'
        before = json.loads((OUT/'baseline_profile.json').read_text())['runs']
        after = json.loads((OUT/'candidate_profile.json').read_text())['runs']
        audit['timing'] = []
        for a, b in zip(before,after):
            assert a['case'] == b['case']
            assert b['wall_s'] < b['input_seconds'], 'Not faster than sample rate'
            assert b['simulated_queue_delay_final_ms'] < 200, 'Final simulated backlog'
            audit['timing'].append(dict(case=a['case'], baseline_wall_s=a['wall_s'],
                                       candidate_wall_s=b['wall_s'], input_seconds=b['input_seconds'],
                                       max_simulated_backlog_ms=b['simulated_queue_delay_max_ms'],
                                       final_simulated_backlog_ms=b['simulated_queue_delay_final_ms']))
        with client.open_sftp() as sftp:
            audit['protected_unchanged'] = all(hashlib.sha256(sftp.open(PROD+'/'+n).read()).hexdigest()==h
                                               for n,h in manifest['protected'].items())
        assert audit['protected_unchanged']
        audit['passed'] = True
        (OUT/'audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
        print(json.dumps(audit,indent=2))
    finally:
        client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--paced-check', action='store_true')
    parser.add_argument('--optimized-check', action='store_true')
    parser.add_argument('--final-check', action='store_true')
    args = parser.parse_args()
    if args.final_check:
        optimized_check(final=True)
    elif args.optimized_check:
        optimized_check()
    elif args.paced_check:
        paced_check()
    else:
        main()
