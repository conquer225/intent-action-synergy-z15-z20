"""Verify completed isolated five-task evidence, without visiting the board."""
import argparse
from collections import Counter
import json
from pathlib import Path

from run_mi_arm_acceptance import digest,dump
from run_mi_multitask import mi_check


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve()
    audit=json.loads((out/'audit.json').read_text(encoding='utf-8'))
    if not audit['passed']:
        raise ValueError('Incomplete/failed orchestration is not a release')
    for path,expected in audit['source_sha256'].items():
        if digest(path)!=expected:
            raise ValueError('Frozen source changed: '+path)
        saved=out/'code_snapshot'/Path(path).name
        if saved.is_file() and digest(saved)!=expected:
            raise ValueError('Frozen snapshot changed: '+str(saved))
    before,after=audit['before'],audit['after']
    assert before['hashes']==after['hashes']
    assert before['services']['guardianloop-web.service']==after['services']['guardianloop-web.service']
    cases={}
    for case in ('baseline','full_load','pause_then_reader_fault'):
        folder=out/case
        report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
        calls=json.loads((folder/'numerical_calls.json').read_text(encoding='utf-8'))
        counts=dict(Counter(row['task'] for row in calls))
        assert not report['monitor_errors'] and not report['remaining_children']
        assert report['packet_input_age_p95_ms']<500 and report['packet_input_age_max_ms']<3000
        assert all(counts.get(task,0)>0 for task in ('emotion','fatigue','seed','ssvep'))
        assert report['packets_consumed']==(37000 if case=='pause_then_reader_fault' else 39000)
        if case=='baseline':
            assert counts.get('mi',0)==0
            assert json.loads((folder/'mi-report.json').read_text())==[]
        else:
            assert counts.get('mi',0)>=6
            mi_check(folder,case=='pause_then_reader_fault')
        cases[case]=dict(actual_calls=counts,report=report,
                        reference=audit['runs'][case]['reference'])
    base,candidate=cases['baseline']['report'],cases['full_load']['report']
    changes=dict(cpu_seconds=(candidate['parent_cpu_seconds']+candidate['children_cpu_seconds']
                    -base['parent_cpu_seconds']-base['children_cpu_seconds']),
                 input_age_p95_ms=candidate['packet_input_age_p95_ms']-base['packet_input_age_p95_ms'],
                 parent_peak_rss_kib=candidate['parent_peak_rss_kib']-base['parent_peak_rss_kib'])
    result=dict(passed=True,protected_files=len(before['hashes']),
                official_web_unchanged=True,all_sources_match=True,cases=cases,
                paired_single_run_changes=changes,
                comparison_limit='One run per condition; not statistical or worst-case speedup. Audit arrays included.',
                live_cyton_verified=False,accuracy_verified=False,production_eligible=False,
                control_enabled=False,pl_changed=False)
    dump(out/'VERIFICATION.json',result)
    print(json.dumps(dict(passed=True,protected_files=result['protected_files'],changes=changes)))


if __name__=='__main__':
    main()
