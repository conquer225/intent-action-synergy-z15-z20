"""Check predeclared gates for the isolated SSVEP A/B replay."""
import json
import argparse

from stage_ssvep_opt_candidate import OUT


def read(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))


def case(name, label):
    report = read(f'{label}_{name}_report.json')
    outputs = read(f'{label}_{name}_primary_results.json')
    rows = [json.loads(line) for line in
            (OUT/f'{label}_{name}_monitor.jsonl').read_text().splitlines()]
    ages = [row['elapsed_seconds']-row['packets_seen']/250 for row in rows
            if row.get('packets_seen') is not None]
    return {'report': {k:report.get(k) for k in
                ('packets_consumed','packets_expected','packet_input_age_p95_ms',
                 'packet_input_age_max_ms','parent_cpu_seconds','children_cpu_seconds',
                 'packet_compute_p99_ms','error','monitor_errors','remaining_children')},
            'total_cpu_s': report['parent_cpu_seconds']+report['children_cpu_seconds'],
            'emotion_predictions': sum((x['result'].get('emotion') or {}).get('state') == 'prediction'
                                       for x in outputs),
            'fatigue_normal': sum(x['result'].get('state') == 'NORMAL' for x in outputs),
            'ssvep_candidate_snapshots': sum((row.get('ssvep') or {}).get('state') == 'candidate_only'
                                             for row in rows),
            'monitor_offset_first20_s': round(sum(ages[:20])/len(ages[:20]),3),
            'monitor_offset_last20_s': round(sum(ages[-20:])/len(ages[-20:]),3),
            'primary_results': outputs}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reverse', action='store_true')
    args = parser.parse_args()
    label = 'paced2' if args.reverse else 'paced'
    manifest = read('candidate_manifest.json')
    base, candidate = case('baseline',label), case('candidate',label)
    metrics = {name:{key:value for key,value in row.items() if key!='primary_results'}
               for name,row in (('baseline',base),('candidate',candidate))}
    b, c = base['report'], candidate['report']
    gates = {
        'event_parity': read('event_parity.json')['passed'],
        'primary_exact': base['primary_results'] == candidate['primary_results'],
        'packets': b['packets_consumed']==c['packets_consumed']==b['packets_expected']==c['packets_expected']==39000,
        'clean_shutdown': all(not row['report'][key] for row in (base,candidate)
                              for key in ('error','monitor_errors','remaining_children')),
        'candidate_p95_lt_500ms': c['packet_input_age_p95_ms'] < 500,
        'candidate_max_lt_3000ms': c['packet_input_age_max_ms'] < 3000,
        'cpu_reduction_ge_10pct': candidate['total_cpu_s'] <= .9*base['total_cpu_s'],
        'service_state_unchanged': manifest[label+'_production_before']==manifest[label+'_production_after'],
        'production_files_unchanged': manifest['production_sha256']==manifest['production_hashes_after'],
    }
    result = {'checks':gates, 'passed':all(gates.values()), 'metrics':metrics,
              'scope':'250Hz paced non-wear bench replay alongside active production; not EEG accuracy or PL benchmark'}
    destination = OUT/(label+'_audit.json')
    if destination.exists():
        raise RuntimeError('Audit already exists; preserve it')
    destination.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
