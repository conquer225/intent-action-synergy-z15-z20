"""Collect exact board artifacts and audit no-fault parity and bounded soak resources."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from eeg_apps_z15.run_soak_stage import ROOT,OUT,PROD,connect,command
from eeg_apps_z15.audit_small_batch import compare,windows


def main():
    p=argparse.ArgumentParser();p.add_argument('--final',action='store_true');args=p.parse_args()
    m=json.loads((OUT/'manifest.json').read_text())
    candidate=json.loads((OUT/'candidate_manifest.json').read_text())
    audit={'no_fault_parity':{},'source':'isolated_board_replay'}
    c=connect()
    try:
        with c.open_sftp() as s:
            def get(remote,local):
                local=OUT/local;local.parent.mkdir(parents=True,exist_ok=True)
                s.get(remote,str(local))
                return local
            get(candidate['stage']+'/tests.txt',Path('candidate/tests.txt'))
            for case in ('recorded','synthetic'):
                actual=get(candidate['stage']+'/parity/'+case+'_0/offline-replay.log',Path('candidate/parity')/case/'replay.log')
                reference=ROOT/'eeg_apps_z15/output/small_batch_async_20260926/replay'/(case+'_0')/'offline-replay.log'
                compare(windows(reference),windows(actual),case)
                audit['no_fault_parity'][case]={'windows':len(windows(actual)),'passed':True}
            fault_dir=candidate.get('fault_dir','faults')
            fault_report=get(candidate['stage']+'/'+fault_dir+'/report.json',Path('candidate/faults/report.json'))
            audit['recovery']=json.loads(fault_report.read_text())
            assert all(x['passed'] for x in audit['recovery']['cases'])
            for case in ('recorded','synthetic'):
                for name in ('replay.log','events.json','status.json','shadow.json'):
                    get(candidate['stage']+'/'+fault_dir+'/'+case+'/'+name,Path('candidate/faults')/case/name)
            for name,sha in m['protected'].items():
                with s.open(PROD+'/'+name,'rb') as f:assert hashlib.sha256(f.read()).hexdigest()==sha,name
            audit['production_unchanged']=True
            if args.final:
                get(candidate['stage']+'/final-tests.txt',Path('candidate/final-tests.txt'))
                for name in ('report.json','producer.json','monitor.jsonl','offline-replay.log','telemetry.json'):
                    get(candidate['stage']+'/freshness_soak/'+name,Path('candidate/freshness_soak')/name)
                fresh=json.loads((OUT/'candidate/freshness_soak/report.json').read_text())
                assert fresh['packets_consumed']==fresh['packets_expected']==15000
                assert fresh['error'] is None and not fresh['monitor_errors'] and not fresh['remaining_children']
                last_payload=json.loads((OUT/'candidate/freshness_soak/telemetry.json').read_text())
                assert 'input_age_at_snapshot_ms' in last_payload['runtime']
                audit['freshness_guard_soak']={'passed':True,'report':fresh}
                for name in ('report.json','producer.json','monitor.jsonl','offline-replay.log','status.json','telemetry.json','shadow.json'):
                    get(candidate['stage']+'/final_soak/'+name,Path('candidate/final_soak')/name)
                short=json.loads((OUT/'candidate/final_soak/report.json').read_text())
                assert short['packets_consumed']==short['packets_expected']==75000
                assert short['error'] is None and not short['monitor_errors'] and not short['remaining_children']
                short_rows=[json.loads(line) for line in (OUT/'candidate/final_soak/monitor.jsonl').read_text().splitlines()]
                short_valid=[r for r in short_rows if r.get('runtime') and r['elapsed_seconds']>10]
                audit['final_candidate_soak']={'passed':True,'report':short,
                    'queue_run_max_ms':max(r['runtime']['reader_queue_delay_max_ms'] for r in short_valid),
                    'snapshot_age_max_s':max(r['snapshot_age_seconds'] for r in short_valid),
                    'display_skipped':short_valid[-1]['runtime']['display_snapshots_skipped'],
                    'note':'Five-minute paced regression after primary-stream recovery repair; concurrent with 30-minute base diagnostics soak.'}
                assert audit['final_candidate_soak']['snapshot_age_max_s']<3
                for name in ('report.json','producer.json','monitor.jsonl','offline-replay.log','status.json','telemetry.json','shadow.json'):
                    get(m['stage']+'/soak/'+name,Path('soak')/name)
                r=json.loads((OUT/'soak/report.json').read_text())
                producer=json.loads((OUT/'soak/producer.json').read_text())
                rows=[json.loads(line) for line in (OUT/'soak/monitor.jsonl').read_text().splitlines()]
                valid=[r for r in rows if r['elapsed_seconds']>10 and r.get('runtime')]
                assert r['error'] is None and not r['monitor_errors']
                assert r['packets_consumed']==r['packets_expected']==producer['packets']==450000
                assert producer['elapsed_seconds']>=1799
                assert not r['remaining_children']
                early=[r['parent']['rss_kib'] for r in rows if 120<=r['elapsed_seconds']<420]
                last=[r['parent']['rss_kib'] for r in rows if r['elapsed_seconds']>=1500]
                growth=float(np.median(last)-np.median(early))
                delay=np.asarray([r['runtime']['reader_queue_delay_ms'] for r in valid])
                age=np.asarray([r['snapshot_age_seconds'] for r in valid])
                final_min=[r['runtime']['reader_queue_delay_ms'] for r in valid if r['elapsed_seconds']>=1740]
                summary={'passed':bool(growth<8192 and max(age)<3 and np.median(final_min)<100),
                         'report':r,'producer':producer,'rss_median_growth_kib':growth,
                         'rss_early_median_kib':float(np.median(early)),'rss_final_median_kib':float(np.median(last)),
                         'queue_sampled_p95_ms':float(np.quantile(delay,.95)),
                         'queue_run_max_ms':max(r['runtime']['reader_queue_delay_max_ms'] for r in valid),
                         'queue_final_minute_median_ms':float(np.median(final_min)),
                         'snapshot_age_p95_s':float(np.quantile(age,.95)),'snapshot_age_max_s':float(max(age)),
                         'stale_observations_after_startup':sum(r['stale'] for r in valid),
                         'sampled_input_age_lower_bound_over_3s':sum(r['snapshot_age_seconds']+r['runtime']['reader_queue_delay_ms']/1000>3 for r in valid),
                         'display_skipped':valid[-1]['runtime']['display_snapshots_skipped'],
                         'monitor_samples':len(rows)}
                audit['soak']=summary
        audit['services_after']=command(c,'systemctl show guardianloop-cyton guardianloop-web -p MainPID -p NRestarts -p ActiveState')
        assert audit['services_after']==m['services_before'],'Unexpected production restart/state change'
        assert command(c,'sha256sum '+PROD+'/guardianloop_pynq.bit '+PROD+'/guardianloop_pynq.hwh')==m['bitstreams']
        audit['bitstreams_unchanged']=True
        (OUT/('audit.json' if args.final else 'candidate_audit.json')).write_text(json.dumps(audit,indent=2))
        print(json.dumps(audit,indent=2))
    finally:c.close()


if __name__=='__main__':main()
