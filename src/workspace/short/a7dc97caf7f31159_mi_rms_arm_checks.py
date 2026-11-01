"""Recorded-only shared-RMS checks; no serial, PL or production configuration."""
import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np
import scipy

from mi_cued_acceptance import logical_replay, recovery, timings, dump
from mi_cued_replay import load_recording
from mi_eegnet_portable import OfflineEEGNet as OriginalEEGNet
from mi_eegnet_rms import OfflineEEGNet as RMSEEGNet
from mi_window_rms import shared_window_rms

FACTORS = np.array([1., .125, .03125])


def logits_in_batches(model, waves):
    rows = []
    for start in range(0, len(waves), 8):
        rows.append(model.logits(waves[start:start+8]))
        if start % 64 == 0:
            print('ARM_RMS_PROBES', start, '/', len(waves), flush=True)
    return np.concatenate(rows)


def kernel_comparison(models, waves):
    for model in models.values():
        for index in range(4):
            model.logits(waves[index:index+1])
    durations = {name: [] for name in models}
    norm_times = []
    for index in range(64):
        values = waves[index % len(waves):index % len(waves)+1]
        started = time.perf_counter()
        shared_window_rms(values)
        norm_times.append((time.perf_counter()-started)*1000)
        names = ('old', 'rms') if index % 2 == 0 else ('rms', 'old')
        for name in names:
            started = time.perf_counter()
            models[name].logits(values)
            durations[name].append((time.perf_counter()-started)*1000)
        if index % 16 == 0:
            print('ARM_RMS_KERNEL', index, '/64', flush=True)
    return dict(single_window={name: timings(values) for name, values in durations.items()},
                shared_rms_only=timings(norm_times), warmup_per_model=4,
                alternating_pairs=64, repeats_independent_people=False)


def verify_candidate_contract(model, path):
    for value in (np.zeros((1,8,500)), np.full((1,8,500), np.nan), np.ones((8,500))):
        try:
            model.logits(value)
        except ValueError:
            continue
        raise AssertionError('Invalid shared-RMS input accepted')
    try:
        OriginalEEGNet(path, allow_experimental=True)
    except ValueError:
        return dict(invalid_inputs_refused=True, original_loader_refused=True)
    raise AssertionError('Old loader accepted new preprocessing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('functional','paced'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    root = Path(__file__).resolve().parent
    models = dict(old=OriginalEEGNet(root/'experimental_eegnet.npz', allow_experimental=True),
                  rms=RMSEEGNet(root/'experimental_rms_eegnet.npz', allow_experimental=True))
    contract = verify_candidate_contract(models['rms'], root/'experimental_rms_eegnet.npz')
    with np.load(root/'probe_input.npz', allow_pickle=False) as data:
        waves, indices = data['waveforms'].copy(), data['indices'].copy()
    with np.load(root/'real_input.npz', allow_pickle=False) as data:
        real, identifiers = data['waveforms'].copy(), data['trial_ids'].copy()
    if waves.shape != (256,8,500) or real.shape != (7,8,500):
        raise ValueError('Fixed 256 source and 7 real windows required')
    raw, sequences = load_recording(root/'bench_input.npz')
    if raw.shape != (39000,8):
        raise ValueError('Frozen156s bench required')
    started, cpu = time.monotonic(), time.process_time()
    kernel = kernel_comparison(models, np.concatenate((waves,real))) if args.mode=='functional' else None
    for name in (('old','rms') if args.mode=='functional' else ('rms',)):
        print('ARM_RMS_MODEL', name, args.mode, flush=True)
        out = args.output/name
        out.mkdir()
        model = models[name]
        probe_logits = logits_in_batches(model, waves)
        np.savez_compressed(out/'probes.npz', indices=indices, logits=probe_logits)
        gain_waves = np.concatenate((waves[:16],real))
        gain_logits = np.stack([logits_in_batches(model, gain_waves*factor) for factor in FACTORS])
        np.savez_compressed(out/'gain_probes.npz', factors=FACTORS, source_indices=indices[:16],
                            trial_ids=identifiers, logits=gain_logits)
        if name=='rms':
            np.testing.assert_allclose(gain_logits[1:], np.repeat(gain_logits[:1],2,axis=0), rtol=0, atol=1e-4)
            np.testing.assert_array_equal(gain_logits.argmax(2), np.repeat(gain_logits[:1].argmax(2),3,axis=0))
        summary = logical_replay(model,raw,sequences,out,paced=args.mode=='paced')
        faults = recovery(model)
        if args.mode=='paced':
            growth = summary['last_decile_median_lateness_ms']-summary['first_decile_median_lateness_ms']
            summary['lateness_growth_ms'] = growth
            if not summary['paced_gate_passed'] or growth >= 50:
                raise AssertionError('Predeclared paced MI gate failed')
        dump(out/'report.json', dict(summary=summary,fault_checks=faults,
              accuracy_scored=False,promotion_gate_passed=False,control_enabled=False))
    rss = None
    if sys.platform.startswith('linux'):
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report = dict(mode=args.mode,kernel_comparison=kernel,contract=contract,
                  numpy=np.__version__,scipy=scipy.__version__,python=sys.version,
                  wall_seconds=time.monotonic()-started,cpu_seconds=time.process_time()-cpu,
                  max_rss_kib=rss,accuracy_scored=False,source='replay',control_enabled=False,
                  scope='isolated MI CPU processing, not sensor-to-display/full production load')
    dump(args.output/'suite.json', report)
    print('ARM_RMS_SUITE_DONE', args.mode, flush=True)


if __name__=='__main__':
    main()
