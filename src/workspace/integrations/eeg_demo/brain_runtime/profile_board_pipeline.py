"""Isolated compute replay. Never opens serial, PL, network or production status files."""
import argparse
import hashlib
import json
import os
import platform
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import scipy

from cyton_sqi import CausalEEGFilter, CytonSQIMonitor, channel_sqi
from cyton_covariance import CovarianceFeatureStream, CovarianceSVM
from cyton_fatigue import FourChannelFatigue, PHYSICAL_INDICES
from seed_shadow import SeedShadow
from seed_quality_runtime import CHANNELS


def summary(values):
    a = np.asarray(values)
    return {"calls": len(a), "total_s": float(a.sum()),
            "median_ms": float(np.median(a) * 1000),
            "p95_ms": float(np.quantile(a, .95) * 1000),
            "max_ms": float(a.max() * 1000)} if len(a) else {}


def run(raw, seq, models, out, filter_chunk):
    elapsed = defaultdict(list)
    def call(name, method, *args, **kwargs):
        start = time.perf_counter()
        result = method(*args, **kwargs)
        elapsed[name].append(time.perf_counter() - start)
        return result

    filt = CausalEEGFilter()
    sqi = CytonSQIMonitor(calibration_windows=15)
    cov = CovarianceFeatureStream(CHANNELS)
    svm = CovarianceSVM(models / 'gameemo_covariance_svm.npz')
    fatigue = FourChannelFatigue(models / 'cyton_fatigue_overlap4.json')
    shadow = SeedShadow(models / 'seed_shadow_weights.npz', CHANNELS,
                        source='replay', status_path=out / 'isolated-shadow.json')
    arrays = defaultdict(list)
    events = []
    filtered = []
    bad = np.r_[False, (np.diff(seq.astype(int)) % 256) != 1]
    batch_times = []
    wall = time.perf_counter()
    cpu = time.process_time()
    for start in range(0, len(raw) - 124, 125):
        stamp = time.perf_counter()
        block = raw[start:start + 125]
        for offset, row in enumerate(block):
            row_index = start + offset
            es = call('seed_shadow_inclusive', shadow.packet, row, int(seq[row_index]),
                      now=row_index / 250, timing_verified=False)
            for e in es:
                events.append({'branch': 'seed', 'row': row_index,
                               **{k: e[k] for k in ('state', 'valid', 'reason', 'class_id',
                                  'accepted_windows', 'warning', 'baseline_updated') if k in e}})
                if 'scores' in e:
                    arrays['seed_scores'].append(e['scores'])
        chunks = [call('prefilter', filt.process, block[i:i + filter_chunk])
                  for i in range(0, len(block), filter_chunk)]
        conditioned = np.concatenate(chunks)
        filtered.extend(conditioned)
        call('emotion_band_filters', cov.append, conditioned)
        call('fatigue_band_filters', fatigue.append, conditioned)
        end = start + 125
        if end % 2000 == 0:
            window = np.asarray(filtered[-2000:])
            window = window - window.mean(axis=0)
            raw_window = raw[end - 2000:end]
            raw_window = raw_window - raw_window.mean(axis=0)
            call('raw_quality', lambda: [channel_sqi(s) for s in raw_window.reshape(4, 500, 8)])
            units = np.rint(window * 100)
            transport = np.all((units >= -32768) & (units <= 32767), axis=0)
            transport &= not bad[end - 2000:end].any()
            quality = call('sqi', sqi.process, window, transport_ok=transport)
            q = [quality['channels'][i]['quality'] if quality['channels'][i]['calibrated'] else 0.
                 for i in cov.indexes]
            # Direct kernels are diagnostic only; never use them to bypass live quality gates.
            if cov.ready:
                feature = call('emotion_covariance_feature', cov.feature)
                pred = call('emotion_svm_diagnostic', svm.predict_feature, feature)
                arrays['emotion_features'].append(feature)
                arrays['emotion_scores'].append(pred[2])
                emotion_ok = min(q) >= .5 and not bad[max(0, end - 3000):end].any()
                events.append({'branch': 'emotion', 'row': end, 'valid': bool(emotion_ok),
                               'class_id': pred[0] if emotion_ok else None})
            features = call('fatigue_de_diagnostic', fatigue.stream.features)
            arrays['fatigue_features'].append(features)
            # Finite uncalibrated DE input times the tree kernel; this is NOT a fatigue estimate.
            score = call('fatigue_tree_diagnostic', fatigue._predict, features)
            arrays['fatigue_kernel_output'].append(score)
            f = call('fatigue_gated_inclusive', fatigue.process_window,
                     all(quality['channels'][i]['quality'] >= .5 for i in PHYSICAL_INDICES),
                     bool(transport[list(PHYSICAL_INDICES)].all()))
            events.append({'branch': 'fatigue', 'row': end,
                           **{k: f[k] for k in ('state', 'valid', 'reason') if k in f}})
        batch_times.append(time.perf_counter() - stamp)
    wall = time.perf_counter() - wall
    cpu = time.process_time() - cpu
    arrays['filtered'] = filtered
    arrays['seed_mean'] = shadow.runtime.mean
    arrays = {k: np.asarray(v) for k, v in arrays.items()}
    report = {'source': 'isolated_offline_replay_not_live', 'filter_chunk': filter_chunk,
              'input_seconds_processed': len(filtered) / 250, 'wall_seconds': wall,
              'cpu_seconds': cpu, 'cpu_single_core_percent_during_compute': cpu / wall * 100,
              'wall_to_input_ratio': wall / (len(filtered) / 250),
              'half_second_batch': summary(batch_times),
              'batches_over_500ms': sum(t > .5 for t in batch_times),
              'stages': {k: summary(v) for k, v in elapsed.items()}, 'events': events,
              'gate_counts': dict(Counter(e['branch'] + ':' + str(e.get('state', e['valid'])) for e in events)),
              'sequence_gaps': int(bad.sum()), 'trailing_samples_not_processed': len(raw) - len(filtered)}
    return arrays, report


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--models', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--repeats', type=int, default=3)
    args = p.parse_args()
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    report = {'platform': platform.platform(), 'numpy': np.__version__, 'scipy': scipy.__version__,
              'thread_env': {k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS')},
              'input_sha256': hashlib.sha256(Path(args.input).read_bytes()).hexdigest(),
              'montage': list(CHANNELS), 'runs': {},
              'scope': 'All ARM branches in one process. 8s feature/gate schedule; extra ungated kernels diagnostic only. '
                       'Excludes USB reader, web requests and production telemetry. SEED includes isolated JSON writes. '
                       'Not the full service loop. 125-sample chunks add up to 496ms batching delay if deployed. '
                       'Existing recording has no true emotion/fatigue labels. Synthetic data is kernel coverage only.'}
    arrays = {}
    with np.load(args.input) as data:
        for case in ('recorded', 'synthetic'):
            for chunk in (1, 125):
                name = case + '_chunk' + str(chunk)
                report['runs'][name] = []
                for repeat in range(args.repeats):
                    a, r = run(data[case], data[case + '_seq'], Path(args.models), out, chunk)
                    report['runs'][name].append(r)
                    if repeat == 0:
                        arrays.update({name + '_' + k: v for k, v in a.items()})
                    print(name, repeat, round(r['wall_seconds'], 3), flush=True)
    try:
        import resource
        report['peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except ImportError:
        report['peak_rss_kib'] = None
    np.savez_compressed(out / 'arrays.npz', **arrays)
    (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
