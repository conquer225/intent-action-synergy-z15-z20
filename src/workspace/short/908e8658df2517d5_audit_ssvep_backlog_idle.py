"""Saved-session diagnostics; no acquisition, deployment or threshold selection."""
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sys
import time

import numpy as np

from audit_ssvep_raw_sync import BASE, CAP, load_capture, read_json, sha256, write_json

OUT = BASE.parent / 'ssvep_backlog_idle_20261002'
RUNTIME = BASE / 'six_trial_analysis/runtime'
sys.path.insert(0, str(RUNTIME))
from ssvep_core import CachedCCA, reference_bank


def fresh_after_guard(row, onset):
    return (row.get('state') == 'candidate_only' and row.get('valid') is True
            and not row.get('stale') and row.get('source') == 'live'
            and 0 <= row['input_age_seconds'] <= .5
            and row['board_monotonic_s'] - (
                row['shadow_updated_monotonic_s'] - row['input_age_seconds']) <= .5
            and row['shadow_updated_monotonic_s'] - row['input_age_seconds'] >= onset + 2.5
            and not (row.get('quality') or {}).get('hard_bad'))


def summarize_rule(rows, decisions, target):
    runs = Counter()
    current, last_hz, last_index = 0, None, None
    retained = []
    for row, keep in zip(rows, decisions):
        hz, index = row.get('frequency_hz'), row['window_end_index_exclusive']
        if not keep:
            current, last_hz, last_index = 0, None, None
            continue
        retained.append(hz)
        current = current + 1 if last_hz == hz and last_index == index-50 else 1
        runs[str(hz)] = max(runs[str(hz)], current)
        last_hz, last_index = hz, index
    return dict(post_guard_fresh_windows=sum(r['_eligible'] for r in rows),
                retained_windows=len(retained),
                retained_candidate_counts=dict(Counter(str(x) for x in retained)),
                longest_consecutive_runs=dict(runs),
                any_three_same_frequency_run=any(n >= 3 for n in runs.values()),
                any_three_target_run=runs[str(target)] >= 3 if target else None,
                independent_accuracy_claimed=False)


def main():
    config = read_json(RUNTIME/'ssvep_causal_protocol.json')
    sos = np.load(RUNTIME/'ssvep_candidate_sos.npy', allow_pickle=False)
    targets = config['frequencies_hz']
    if config['fixed_cap'] != CAP or targets != [8, 10, 12, 14]:
        raise ValueError('Unexpected fixed protocol')
    references = reference_bank(targets, samples=500, sample_rate_hz=250,
                                harmonics=config['harmonics'])
    competitors = [float(f) for f in np.arange(7.5, 15, .5) if f not in targets]
    decoder = CachedCCA(references)
    off_grid = CachedCCA(reference_bank(competitors, samples=500,
                                       sample_rate_hz=250, harmonics=config['harmonics']))
    all_windows, backlog, trials, gaps = [], [], [], []
    parity_errors, competitor_cost_ms = [], []
    ids = read_json(BASE/'diagnostic_capture_segments.json')['capture_ids']
    for recording_id in ids:
        capture = load_capture(recording_id, sos)
        primary = [json.loads(s) for s in
                   (capture['folder']/'window_results.jsonl').read_text().splitlines()]
        boundaries = np.asarray([r['packets_seen'] for r in primary], dtype=np.int64)
        for start in (r for r in capture['events'] if r['event'] == 'trial_start'):
            events = [r for r in capture['events'] if r['trial_id'] == start['trial_id']]
            onset = next(r['board_monotonic_s'] for r in events
                         if r['event'] == 'presentation_receipt')
            rows = [dict(r, _eligible=fresh_after_guard(r, onset)) for r in events
                    if r['event'] == 'shadow_snapshot']
            for row in rows:
                watermark = row['packets_seen']
                position = int(np.searchsorted(capture['indices'], watermark-1))
                if position >= len(capture['indices']) or capture['indices'][position] != watermark-1:
                    raise ValueError('Cue/raw watermark mismatch')
                previous = int(np.searchsorted(boundaries, watermark, side='right'))-1
                distance = watermark-int(boundaries[previous]) if previous >= 0 else None
                lo = max(0, position-500)
                receive_gap = float(np.diff(capture['arrival'][lo:position+1]).max())
                info = dict(trial_id=start['trial_id'], target_hz=start['target_hz'],
                    recording_id=recording_id, packets_seen=watermark,
                    samples_after_primary_window=distance,
                    input_age_ms=row['input_age_seconds']*1000,
                    state=row['state'], reason=row.get('reason'),
                    max_usb_receive_gap_in_previous_2s_ms=receive_gap*1000)
                all_windows.append(info)
                gaps.append(receive_gap)
                if row.get('reason') == 'input_backlog':
                    backlog.append(info)
                row['_off_grid_ok'] = False
                if row['_eligible']:
                    if position < 499 or capture['reset'][position-499:position+1].any():
                        raise ValueError('Eligible reconstructed window crosses reset')
                    x = capture['filtered'][position-499:position+1].T
                    scores = decoder.scores(x)
                    parity_errors.append(float(np.max(np.abs(scores-row['scores']))))
                    began = time.perf_counter()
                    competing = off_grid.scores(x)
                    competitor_cost_ms.append((time.perf_counter()-began)*1000)
                    row['_off_grid_ok'] = bool(max(scores) > max(competing))
                    row['_competing_best_hz'] = competitors[int(np.argmax(competing))]
                    row['_competing_score'] = float(max(competing))
            masks = {
                'closed_set': [r['_eligible'] for r in rows],
                'score_030_margin_005': [r['_eligible'] and max(r['scores']) >= .30
                                        and r['margin'] >= .05 for r in rows],
                'score_040_margin_010': [r['_eligible'] and max(r['scores']) >= .40
                                        and r['margin'] >= .10 for r in rows],
                'off_grid_competitor': [r['_eligible'] and r['_off_grid_ok'] for r in rows],
            }
            eligible = [r for r in rows if r['_eligible']]
            trials.append(dict(trial_id=start['trial_id'], target_hz=start['target_hz'],
                observed_windows=len(rows), all_snapshot_states=dict(Counter(r['state'] for r in rows)),
                eligible_score_range=[min(max(r['scores']) for r in eligible),
                                      max(max(r['scores']) for r in eligible)] if eligible else None,
                eligible_margin_range=[min(r['margin'] for r in eligible),
                                       max(r['margin'] for r in eligible)] if eligible else None,
                exploratory_rules={k:summarize_rule(rows, v, start['target_hz'])
                                   for k,v in masks.items()},
                competitor_winners=dict(Counter(str(r['_competing_best_hz']) for r in eligible))))
    def grouped(condition):
        selected = [r for r in all_windows if condition(r)]
        return dict(windows=len(selected), backlog_windows=sum(r['reason']=='input_backlog' for r in selected))
    summary = dict(created_pc_local=datetime.now().isoformat(),
        input_audit_hashes={i:sha256(BASE/'recordings'/i/'capture_audit.json') for i in ids},
        runtime_hashes={p.name:sha256(p) for p in RUNTIME.iterdir() if p.is_file()},
        script_sha256=sha256(Path(__file__)), fixed_cap=CAP, controls_enabled=False,
        formal_runtime_changed=False, thresholds_selected_for_deployment=False,
        total_snapshots=len(all_windows), backlog_events=backlog,
        all_snapshot_timing=all_windows,
        backlog_distance_counts=dict(Counter(str(r['samples_after_primary_window']) for r in backlog)),
        distance_groups={
            'first_50_samples_after_primary':grouped(lambda r:r['samples_after_primary_window'] is not None
                                                     and 0 <= r['samples_after_primary_window'] < 50),
            '50_to_149_samples':grouped(lambda r:r['samples_after_primary_window'] is not None
                                        and 50 <= r['samples_after_primary_window'] < 150),
            '150_or_more_samples':grouped(lambda r:r['samples_after_primary_window'] is not None
                                          and r['samples_after_primary_window'] >= 150)},
        max_usb_receive_gap_in_cue_windows_ms=max(gaps)*1000,
        reconstructed_score_max_abs_error=max(parity_errors),
        reconstructed_score_p95_abs_error=float(np.quantile(parity_errors,.95)),
        off_grid_competitors_hz=competitors,
        off_grid_pc_cost_median_ms=float(np.median(competitor_cost_ms)),
        trials=trials,
        limitations=['Single wearer; overlapping windows are not independent labeled trials',
                     'Exploratory rules are not selected or independently validated',
                     'Raw USB timing is not optical onset or ADC hardware timing',
                     'Reconstructed filter starts at capture boundary; live state not available',
                     'Boundary association alone cannot identify the exact slow CPU stage'])
    write_json(OUT/'saved_session_diagnostics.json', summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in
                     ('trials','backlog_events','all_snapshot_timing','runtime_hashes','limitations')}, ensure_ascii=False))
    for t in trials:
        print(json.dumps(t, ensure_ascii=False))


if __name__ == '__main__':
    main()
