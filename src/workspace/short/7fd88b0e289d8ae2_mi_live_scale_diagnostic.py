"""Audit frozen MI scaling and source/live preprocessing without fitting a model."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import time

# Load Torch before the SciPy/MNE dependency stack on Windows.
from mi_comparison_models import EEGNetSmall, channel_scaler, network_logits, normalized_tensor, torch
import numpy as np
import scipy
from scipy import signal

from cho2017_data import FIXED, load_subject
from cho2017_features import _filtered_epoch
from cyton_sqi import CausalEEGFilter
from mi_eegnet_portable import OfflineEEGNet

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / 'mi_live_scale_diagnostic_protocol.json'
PACKETS = np.dtype([('ordinal', '<u8'), ('received_monotonic_s', '<f8'),
                    ('sequence', 'u1'), ('malformed_bytes', '<u4'), ('adc', '<i4', (8,))])
ADC_UV = 4_500_000 / 24 / (2**23 - 1)


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def quantiles(values):
    return dict(zip(('min', 'p01', 'p10', 'median', 'p90', 'p99', 'max'),
                    np.quantile(values, [0, .01, .1, .5, .9, .99, 1], axis=0).tolist()))


def energy_summary(waves, mean):
    centered = waves.astype(np.float64) - mean[None, :, None]
    energies = np.sum(centered**2, axis=(1, 2))
    order = np.argsort(-energies, kind='stable')
    count = max(1, int(np.ceil(len(energies) * .01)))
    return energies, order, float(energies[order[:count]].sum() / energies.sum())


def source_groups(waves, subjects, labels, logits, mean, scale):
    rms = np.sqrt(np.mean((waves.astype(np.float64) - mean[None, :, None])**2, axis=(1, 2)))
    edges = np.quantile(rms, [.25, .5, .75])
    bins = np.searchsorted(edges, rms, side='right')
    rows = []
    for index in range(4):
        selected = bins == index
        rows.append({'quartile_low_to_high': index + 1, 'count': int(selected.sum()),
                     'rms_uv_range': [float(rms[selected].min()), float(rms[selected].max())],
                     'left_prediction_fraction': float(np.mean(logits[selected].argmax(axis=1) == 0)),
                     'true_left_fraction': float(np.mean(labels[selected] == 0))})
    per_person = []
    for person in np.unique(subjects):
        selected = subjects == person
        per_person.append({'person': int(person), 'count': int(selected.sum()),
                           'median_rms_uv': float(np.median(rms[selected])),
                           'left_prediction_fraction': float(np.mean(logits[selected].argmax(axis=1) == 0))})
    return {'channel_std_uv_quantiles': quantiles(waves.std(axis=2, dtype=np.float64)),
            'normalized_channel_std_quantiles': quantiles(waves.std(axis=2, dtype=np.float64) / scale),
            'amplitude_quartile_responses': rows, 'per_person': per_person}


def main(output):
    if output.exists():
        raise RuntimeError('Preserve previous diagnostics; use a fresh output path')
    protocol = read_json(PROTOCOL)
    if protocol['channels'] != list(FIXED) or protocol['board_access']:
        raise ValueError('Fixed montage or offline scope changed')
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True)
    np.random.seed(protocol['seed'])
    started = time.monotonic()
    cache = HERE / protocol['source_cache']
    provenance = read_json(cache / 'provenance.json')
    for name, expected in provenance['cache_sha256'].items():
        if digest(cache / name) != expected:
            raise ValueError('Source cache hash changed: ' + name)
    portable = OfflineEEGNet(HERE / protocol['model'], allow_experimental=True)
    meta = portable.metadata['source_metadata']
    folds = read_json(cache / 'fold_manifest.json')
    frozen = next(row for row in folds if row['target'] == protocol['source_target_excluded'])
    if any(meta[key] != frozen[key] for key in ('fit_people', 'validation_people', 'target')):
        raise ValueError('Model no longer matches its frozen fold')
    with np.load(cache / 'statistics.npz', allow_pickle=False) as data:
        subjects, labels = data['subjects'].copy(), data['labels'].copy()
    if sorted(np.unique(subjects).tolist()) != protocol['allowed_source_people']:
        raise ValueError('Only original training group may be loaded')
    if set(subjects) & set(protocol['confirmation_people_forbidden']):
        raise ValueError('Confirmation people must not be reopened')
    waves = np.load(cache / 'waveforms.npy', mmap_mode='r', allow_pickle=False)
    fitting = np.flatnonzero(np.isin(subjects, meta['fit_people']))
    validation = np.flatnonzero(np.isin(subjects, meta['validation_people']))
    mean, scale = channel_scaler(waves[fitting])
    np.testing.assert_allclose(mean, portable.mean, rtol=0, atol=1e-10)
    np.testing.assert_allclose(scale, portable.scale, rtol=0, atol=1e-10)
    model = EEGNetSmall(portable.metadata['config'])
    state = model.state_dict()
    for key, values in portable.weights.items():
        state[key] = torch.from_numpy(values.astype(np.float32))
    model.load_state_dict(state)
    model.eval()
    result = {'scope': protocol['scope'], 'started_at': datetime.now().astimezone().isoformat(),
              'channels': list(FIXED), 'fit_people': meta['fit_people'], 'validation_people': meta['validation_people'],
              'excluded_target': meta['target'], 'source_mean': mean.tolist(), 'source_scale': scale.tolist(),
              'scale_reproduction_max_error': float(np.max(np.abs(scale - portable.scale))),
              'mean_reproduction_max_error': float(np.max(np.abs(mean - portable.mean))),
              'source_model': portable.metadata, 'files_sha256': {str(path): digest(path) for path in
                  [Path(__file__), PROTOCOL, HERE / protocol['model'], cache / 'provenance.json']},
              'cache_sha256': provenance['cache_sha256'],
              'software': {'python': sys.version, 'torch': torch.__version__, 'numpy': np.__version__, 'scipy': scipy.__version__},
              'board_accessed': False, 'model_fitted': False, 'formal_files_modified': False}
    energies, energy_order, fraction = energy_summary(waves[fitting], mean)
    manifest = read_json(cache / 'trial_manifest.json')
    top_count = max(1, int(np.ceil(len(fitting) * .01)))
    top = fitting[energy_order[:top_count]]
    flagged = np.array([row['voltage_bad'] or row['emg_bad'] for row in manifest])
    without_top = fitting[energy_order[top_count:]]
    _, counterfactual_scale = channel_scaler(waves[without_top])
    result['energy_dominance'] = {'fit_count': len(fitting), 'top_one_percent_count': top_count,
        'top_one_percent_fraction': fraction, 'dominance_hypothesis_passed': fraction > .5,
        'top_one_percent_author_flagged_count': int(flagged[top].sum()),
        'all_fit_author_flagged_fraction': float(flagged[fitting].mean()),
        'counterfactual_scale_without_top_uv_not_used': counterfactual_scale.tolist(),
        'largest_trials': [{'cache_index': int(i), **manifest[i], 'energy_fraction': float(energies[j] / energies.sum())}
                           for j, i in zip(energy_order[:10], fitting[energy_order[:10]])]}
    for name, indices in [('fitting', fitting), ('source_validation', validation)]:
        logits = network_logits(model, normalized_tensor(waves[indices], mean, scale, 'cpu'))
        result[name] = source_groups(waves[indices], subjects[indices], labels[indices], logits, mean, scale)
        parity = portable.logits(waves[indices[:8]])
        np.testing.assert_allclose(logits[:8], parity, rtol=0, atol=1e-5)
        result[name]['torch_portable_logit_max_error'] = float(np.max(np.abs(logits[:8] - parity)))
    print('Source distribution and frozen inference complete', flush=True)
    original = read_json(HERE / 'cho2017_protocol.json')
    median_index = fitting[np.argsort(energies, kind='stable')[len(energies) // 2]]
    examples = [int(fitting[energy_order[0]]), int(fitting[energy_order[1]]), int(median_index)]
    raw_checks = []
    for i in examples:
        row = manifest[i]
        person = load_subject(row['subject'])
        index = row['original_order']
        if int(person.labels[index]) != row['label'] or int(person.original_keys[index]) != row['original_sequence_key']:
            raise ValueError('Original trial identity changed')
        bands, start, stop = _filtered_epoch(person.samples[index], person.cue_sample, original)
        recomputed = bands[2][start:stop].T.astype(np.float32)
        np.testing.assert_array_equal(recomputed, waves[i])
        raw_checks.append({'cache_index': i, **row, 'raw_cache_max_error_uv': float(np.max(np.abs(recomputed - waves[i]))),
                           'filtered_std_uv': recomputed.std(axis=1, dtype=np.float64).tolist()})
        del person
    result['source_raw_reextraction'] = raw_checks
    up, down = 125, 256
    fir = up * signal.firwin(5121, 1 / down, window=('kaiser', 5))
    fir_rows = []
    for frequency in (10, 20):
        input_values = np.sin(2 * np.pi * frequency * np.arange(512 * 10) / 512)
        converted = signal.upfirdn(fir, input_values, up, down)[:2500]
        expected = np.sin(2 * np.pi * frequency * (np.arange(2500) / 250 - 2560 / (512 * up)))
        fir_rows.append({'frequency_hz': frequency, 'steady_rms_gain': float(np.std(converted[500:2000]) / np.std(expected[500:2000])),
                         'steady_expected_max_error': float(np.max(np.abs(converted[500:2000] - expected[500:2000])))})
    result['fir_checks'] = fir_rows
    capture = HERE / protocol['capture']
    audit = read_json(capture / 'AUDIT.json')
    packets = np.fromfile(capture / 'packets.bin', dtype=PACKETS)
    if len(packets) != 150000 or not np.array_equal(packets['ordinal'], np.arange(1, len(packets) + 1)):
        raise ValueError('Expected complete 10 minute sequential raw capture')
    raw = packets['adc'].astype(np.float64) * ADC_UV
    result['raw_capture_hashes'] = {p.name: digest(p) for p in [capture / 'packets.bin', capture / 'events.jsonl', capture / 'AUDIT.json']}
    result['live_diagnostics'] = []
    for trial in audit['trials']:
        path = capture / (trial['trial_id'] + '.npz')
        with np.load(path, allow_pickle=False) as data:
            waveform = data['filtered_uv'].copy()
            first, stop = int(data['window_start']), int(data['window_end_exclusive'])
        factors = protocol['live_amplitude_factors']
        logits = portable.logits(np.concatenate([waveform * factor for factor in factors]))
        reset_start = max(0, first - 1750)
        segment = raw[reset_start:stop]
        car = segment - segment.mean(axis=1, keepdims=True)
        conditioned = CausalEEGFilter().process(car)
        band = signal.sosfilt(signal.butter(4, [8, 30], fs=250, btype='bandpass', output='sos'), conditioned, axis=0)
        reset_wave = band[-500:].T[None]
        result['live_diagnostics'].append({'trial_id': trial['trial_id'], 'cue_intention_only': trial['target'],
            'saved_npz_sha256': digest(path), 'source': trial['source'],
            'filtered_std_uv': waveform.std(axis=2)[0].tolist(),
            'sensitivity_no_factor_selected': [{'factor': f, 'logits': score.tolist(), 'output': ['left', 'right'][int(np.argmax(score))]}
                                                 for f, score in zip(factors, logits)],
            'reset_after_7s_max_error_uv': float(np.max(np.abs(reset_wave - waveform))),
            'reset_after_7s_relative_rms_error': float(np.linalg.norm(reset_wave-waveform) / np.linalg.norm(waveform)),
            'reset_logits': portable.logits(reset_wave)[0].tolist()})
    result['elapsed_s'] = time.monotonic() - started
    result['completed_at'] = datetime.now().astimezone().isoformat()
    output.mkdir(parents=True)
    (output / 'diagnostic.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    (output / 'protocol.json').write_text(PROTOCOL.read_text(encoding='utf-8'), encoding='utf-8')
    print(json.dumps({'output': str(output), 'top_one_percent_energy': fraction, 'elapsed_s': result['elapsed_s']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
