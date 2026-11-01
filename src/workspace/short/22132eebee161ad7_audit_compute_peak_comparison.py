"""Audit fixed-input engineering replay; never infer wearer accuracy."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np

from pl_filter_pipeline_candidate.compare_seed_event_audits import compare, equivalent, load_events


ROOT = Path(__file__).resolve().parents[1]
CASES = ('baseline', 'array', 'array_async_seed')
CHANNELS = ['F3', 'F4', 'C3', 'C4', 'T7', 'T8', 'O1', 'O2']
INPUT = ROOT / 'eeg_apps_z15/output/ssvep_backlog_idle_20261002/arm_replay_profile/input.npz'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def primary_parity(reference, candidate):
    mismatches = [i for i, (a, b) in enumerate(zip(reference, candidate)) if not equivalent(a, b)]
    pairs = [(a['result']['emotion']['pair_scores'], b['result']['emotion']['pair_scores'])
             for a, b in zip(reference, candidate)
             if 'pair_scores' in a['result'].get('emotion', {}) and
                'pair_scores' in b['result'].get('emotion', {})]
    return dict(reference_publications=len(reference), candidate_publications=len(candidate),
        mismatch_indices=mismatches,
        prediction_score_max_abs_difference=max((float(np.max(np.abs(np.asarray(a)-b)))
                                                 for a, b in pairs), default=None),
        passed=len(reference) == len(candidate) and not mismatches)


def performance_gates(base, candidate, plan):
    ratios = dict(
        feature_max_reduction=1-candidate['feature_max_ms']/base['feature_max_ms'],
        input_age_p95_reduction=1-candidate['input_age_p95_ms']/base['input_age_p95_ms'],
        input_age_max_increase=candidate['input_age_max_ms']/base['input_age_max_ms']-1,
        cpu_total_increase=candidate['total_cpu_seconds']/base['total_cpu_seconds']-1)
    gates = dict(
        feature_max_at_least_50pct_lower=ratios['feature_max_reduction'] >= plan['min_feature_max_speedup_fraction'],
        input_age_p95_at_least_15pct_lower=ratios['input_age_p95_reduction'] >= plan['min_age_p95_improvement_fraction'],
        input_age_max_not_worse=candidate['input_age_max_ms'] <= base['input_age_max_ms'],
        cpu_total_increase_at_most_10pct=ratios['cpu_total_increase'] <= plan['max_cpu_total_increase_fraction'])
    return dict(ratios=ratios, gates=gates, passed=all(gates.values()))


def raw_audit(run, expected, sequences):
    directories = sorted(path for path in (run/'recordings').iterdir() if path.is_dir())
    if len(directories) != 1:
        raise ValueError('Expected one private replay recording')
    path = directories[0]
    metadata = read(path/'metadata.json')
    counts = np.fromfile(path/'samples_i32le.bin', dtype='<i4').reshape(-1, 8)
    expected_counts = np.rint(expected / metadata['microvolts_per_count']).astype('<i4')
    checks = dict(
        samples_match=np.array_equal(counts, expected_counts),
        sequences_match=np.array_equal(np.fromfile(path/'sequence_u8.bin', dtype='u1'), sequences),
        indexes_match=np.array_equal(np.fromfile(path/'stream_index_u64le.bin', dtype='<u8'), np.arange(len(expected))),
        flags_clean=np.array_equal(np.fromfile(path/'flags_u8.bin', dtype='u1'), np.zeros(len(expected), dtype='u1')),
        channel_map_match=metadata['channel_map'] == CHANNELS,
        first_index_correct=metadata['stream_first_index'] == 0,
        no_live_label=metadata['protocol']['source'] == 'offline_replay_not_live' and
                      metadata['participant_id'] == 'OFFLINE_REPLAY_NOT_NEW_HUMAN_DATA',
        control_disabled=metadata['protocol']['control_enabled'] is False)
    arrivals = np.fromfile(path/'arrival_mono_f64le.bin', dtype='<f8')
    checks['arrival_rows_finite_ordered'] = (len(arrivals) == len(expected) and
        bool(np.isfinite(arrivals).all()) and bool((np.diff(arrivals) >= 0).all()))
    return dict(checks=checks, passed=all(checks.values()), samples=len(counts),
        signal_sha256=sha256(path/'samples_i32le.bin'),
        note='Arrival timestamps are replay receive times, not ADC or optical onset times.')


def case_audit(directory, expected, sequences):
    run = directory/'run'
    report, stages = read(run/'report.json'), read(run/'stages.json')['stages']
    publications = read(run/'primary_results.json')
    seed = read(run/'seed.final.json')
    ssvep = read(run/'ssvep.final.json')
    primary = read(run/'primary.final.json')
    monitoring = [json.loads(line) for line in (run/'monitor.jsonl').read_text().splitlines()]
    checks = dict(all_input_consumed=report['packets_consumed'] == len(expected) == report['packets_expected'],
        no_repeat=report['input_repeated'] is False, arm_only=report['filter_backend'] == 'arm',
        no_runtime_error=report['error'] is None, no_monitor_error=not report['monitor_errors'],
        no_children_remaining=not report['remaining_children'],
        primary_withdrawn=primary['valid'] is False and primary['emotion']['valid'] is False,
        seed_withdrawn=seed['valid'] is False, ssvep_withdrawn=ssvep['valid'] is False,
        ssvep_control_disabled=ssvep['control_enabled'] is False,
        publications_explicitly_offline=all(p['result']['source'] == 'offline_replay_not_live' and
            p['result']['real'] is False and p['result']['offline'] is True for p in publications))
    metrics = dict(input_age_p95_ms=report['packet_input_age_p95_ms'],
        input_age_max_ms=report['packet_input_age_max_ms'], compute_p99_ms=report['packet_compute_p99_ms'],
        compute_max_ms=report['packet_compute_max_ms'], parent_cpu_seconds=report['parent_cpu_seconds'],
        children_cpu_seconds=report['children_cpu_seconds'],
        total_cpu_seconds=report['parent_cpu_seconds']+report['children_cpu_seconds'],
        parent_peak_rss_kib=report['parent_peak_rss_kib'],
        monitored_aggregate_rss_peak_kib=max(row['parent']['rss_kib'] + sum(c['rss_kib'] for c in row['children'])
                                          for row in monitoring),
        feature_calls=stages['emotion_feature']['calls'], feature_wall_ms=1000*stages['emotion_feature']['wall_s'],
        feature_cpu_ms=1000*stages['emotion_feature']['cpu_s'],
        feature_max_ms=1000*stages['emotion_feature']['max_wall_s'], wall_seconds=report['wall_seconds'])
    raw = raw_audit(run, expected, sequences)
    event_count = Counter(p['result']['emotion'].get('state') for p in publications)
    fatigue_windows = sorted({p['result']['last_inference_window'] for p in publications
                              if p['result'].get('state') == 'NORMAL'})
    return dict(checks=checks, raw_recording=raw, metrics=metrics,
        emotion_state_counts=dict(event_count), fatigue_normal_inference_windows=fatigue_windows,
        monitor_ssvep_state_counts=dict(Counter(row.get('ssvep', {}).get('state') for row in monitoring)),
        engineering_passed=all(checks.values()) and raw['passed'])


def build(directory):
    plan = read(directory/'PLAN.json')
    if sha256(INPUT) != plan['input_sha256']:
        raise ValueError('Frozen input hash mismatch')
    with np.load(INPUT, allow_pickle=False) as source:
        expected, sequences = source['recorded'], source['recorded_seq']
    cases = {name: case_audit(directory/name, expected, sequences) for name in CASES
             if (directory/name/'run/report.json').exists()}
    if 'baseline' not in cases:
        raise ValueError('Completed baseline required')
    reference = read(directory/'baseline/run/primary_results.json')
    comparisons = {}
    for name in CASES[1:]:
        if name not in cases:
            continue
        primary = primary_parity(reference, read(directory/name/'run/primary_results.json'))
        seed = compare(directory/'baseline/run/seed.events.jsonl', directory/name/'run/seed.events.jsonl')
        reference_events = load_events(directory/'baseline/run/seed.events.jsonl')
        candidate_events = load_events(directory/name/'run/seed.events.jsonl')
        reference_predictions = [e['event'] for e in reference_events if e['event']['state'] == 'prediction']
        candidate_predictions = [e['event'] for e in candidate_events if e['event']['state'] == 'prediction']
        seed_diagnostic = dict(
            reference_prediction_count=len(reference_predictions),
            candidate_prediction_count=len(candidate_predictions),
            prediction_payloads_equivalent=equivalent(reference_predictions, candidate_predictions),
            extra_wait_events=[dict(index=i, input_age_ms=e['input_age_ms'], event=e['event'])
                for i, e in enumerate(candidate_events) if e['event'].get('reason') == 'waiting_for_packets'],
            scope='Diagnosis only. Matching predictions does not override the strict all-event gate.')
        performance = performance_gates(cases['baseline']['metrics'], cases[name]['metrics'], plan)
        comparisons[name] = dict(primary=primary, seed=seed, seed_diagnostic=seed_diagnostic, performance=performance,
            all_declared_gates_passed=cases[name]['engineering_passed'] and primary['passed'] and
                seed['verdict'] == 'pass' and performance['passed'])
    preservation = read(directory/'preservation.json')
    snapshot = directory/'code_snapshot'
    code_matches = all(sha256(snapshot/name) == digest for name, digest in plan['harness_hashes'].items())
    code_matches = code_matches and sha256(snapshot/'cyton_covariance.py') == plan['candidate_covariance_sha256']
    return dict(scope='Same-input isolated ARM engineering replay; no new model, accuracy or PL speedup claim.',
        samples_per_case=len(expected), seconds_per_case=plan['seconds_per_case'], channel_map=CHANNELS,
        input_sha256=plan['input_sha256'], frozen_code_snapshot_matches=code_matches,
        completed_cases=list(cases), missing_cases=[name for name in CASES if name not in cases],
        preservation=preservation, cases=cases, comparisons=comparisons,
        deployment_changed=False,
        limitations=['One run per case, fixed order and cold worker initialization; not statistical evidence.',
            'Controller interrupted during array case; its board job completed without repeating data. Third case separately authorized.',
            'Network/browser rendering excluded. Idle-stimulation false positives are not solved by a load optimization.',
            'This input has no injected midstream gap. End-of-stream withdrawal and separate worker fault unit tests are covered.',
            'SSVEP windows were computed, but this load trace has no cue labels and no every-window SSVEP score audit.',
            'Monitored summed RSS double-counts shared pages; it is not physical-memory usage. CPU includes children.',
            'Run report scope contains a legacy "repeated recorded trace" phrase; input_repeated=false and binary equality are authoritative.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    result = build(args.directory)
    (args.directory/'AUDIT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(completed_cases=result['completed_cases'], missing_cases=result['missing_cases'],
        preservation=result['preservation'], comparisons=result['comparisons']), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
