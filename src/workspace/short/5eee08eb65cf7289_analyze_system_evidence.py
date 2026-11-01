"""Machine-readable numerical/queue regression checks for the isolated run."""
import json
import argparse
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parent/'output/unified_hdmi_20261007'
OLD=OUT.parent/'long_cache_20261007/eeg-compact-load'


def comparable(value):
    keys=('window','packets_seen','valid','state','level','perclos','smoothed_perclos',
          'last_inference_window','calibration_current','signal_quality','emotion','sqi')
    return {key:value.get(key) for key in keys}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--label',default='eeg-page-scheduled')
    args=parser.parse_args();folder=OUT/args.label
    old=json.loads((OLD/'primary_results.json').read_text())
    new=json.loads((folder/'primary_results.json').read_text())
    reference={item['result']['window']:comparable(item['result']) for item in old
               if item['result'].get('valid')}
    common=[item['result'] for item in new if item['result'].get('valid')
            and item['result'].get('window') in reference]
    different=[value['window'] for value in common if comparable(value)!=reference[value['window']]]
    result=dict(common_primary_windows=len(common),different_primary_windows=different,
                exact_published_primary_values_match=bool(common) and not different)
    report=json.loads((folder/'report.json').read_text())
    result['replay']={key:report.get(key) for key in ('packets_consumed','packets_expected',
        'packet_input_age_p95_ms','packet_input_age_max_ms','error','remaining_children')}
    result['stages']=[]
    for path in OUT.glob('play-system-*-report.json'):
        video=json.loads(path.read_text());stages=video.get('frame_stage_times',[])
        result['stages'].append(dict(session=path.stem,frames=video.get('frames'),
            fps=video.get('fps'),minimum_full_second_frames=video.get('minimum_full_second_frames'),
            p95_copy_flush_ms=float(np.quantile([row['copy_flush_ms'] for row in stages],.95)) if stages else None,
            p95_latch_scan_ms=float(np.quantile([row['latch_scan_ms'] for row in stages],.95)) if stages else None))
    monitor=[json.loads(line) for line in (folder/'monitor.jsonl').read_text().splitlines()]
    result['ssvep_resume_observed']=any(row.get('ssvep',{}).get('packets_seen',0)>0 for row in monitor)
    result['ssvep_final_valid']=monitor[-1].get('ssvep',{}).get('valid')
    result['seed_accepted_windows']=max(row.get('seed',{}).get('accepted_windows',0) for row in monitor)
    mi=json.loads((folder/'mi-report.json').read_text())
    result['mi']=[dict(candidate_count=len(worker['candidates']),
        http_errors=worker['http_errors'],adapter_error=worker['adapter_error'],
        threads_stopped=worker['threads_stopped'],
        final_result_revoked=worker['final']['result'] is None,
        physical_control_enabled=worker['final']['control_enabled']) for worker in mi]
    result['scope']='Old unlabeled EEG replay, scripted pages, compact cache fitted inside central menu, silent; not live input/accuracy/motor acceptance'
    (OUT/(args.label+'-checks.json')).write_text(json.dumps(result,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
