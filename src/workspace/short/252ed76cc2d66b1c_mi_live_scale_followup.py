"""Label-blind counterfactuals following the completed MI scale audit."""
import argparse
import json
from pathlib import Path

from mi_live_scale_diagnostic import (HERE, PACKETS, ADC_UV, digest, read_json, torch,
                                    EEGNetSmall, normalized_tensor, network_logits,
                                    OfflineEEGNet, CausalEEGFilter, np, signal)
from cho2017_data import PICKS, load_subject
from cho2017_features import _filtered_epoch
from scipy.io import loadmat


def run(output):
    if output.exists():
        raise RuntimeError('Use a fresh output path; previous results are preserved')
    protocol_path = HERE / 'mi_live_scale_followup_protocol.json'
    protocol = read_json(protocol_path)
    first = HERE / 'output/mi_live_scale_diagnostic_20261003/diagnostic.json'
    diagnostic = read_json(first)
    root = HERE / 'output/mi_model_comparison_20261001'
    source = read_json(root / 'provenance.json')
    for name, expected in source['cache_sha256'].items():
        if digest(root / name) != expected:
            raise ValueError('Source cache changed: ' + name)
    torch.set_num_threads(4)
    portable = OfflineEEGNet(HERE / 'output/mi_cued_delivery_20261002_final/experimental_eegnet.npz', allow_experimental=True)
    if protocol['source_people'] != portable.metadata['source_metadata']['validation_people']:
        raise ValueError('Only the frozen source-validation people may be used')
    model = EEGNetSmall(portable.metadata['config'])
    state = model.state_dict()
    for key, value in portable.weights.items():
        state[key] = torch.from_numpy(value.astype(np.float32))
    model.load_state_dict(state)
    model.eval()
    with np.load(root / 'statistics.npz', allow_pickle=False) as data:
        indices = np.flatnonzero(np.isin(data['subjects'], protocol['source_people']))
    waves = np.load(root / 'waveforms.npy', mmap_mode='r', allow_pickle=False)[indices]
    result = {'protocol': protocol, 'protocol_sha256': digest(protocol_path),
              'script_sha256': digest(Path(__file__)), 'first_diagnostic_sha256': digest(first),
              'source_amplitude_counterfactuals': [], 'live_warmup_counterfactuals': [],
              'board_accessed': False, 'accuracy_scored': False, 'model_fitted': False}
    for factor in protocol['source_amplitude_factors']:
        logits = network_logits(model, normalized_tensor(waves * factor, portable.mean, portable.scale, 'cpu'))
        result['source_amplitude_counterfactuals'].append({'factor': factor, 'windows': len(waves),
            'left_prediction_fraction': float(np.mean(logits.argmax(axis=1) == 0)),
            'logit_margin_left_minus_right_median': float(np.median(logits[:,0] - logits[:,1]))})
    raw_root = Path('D:/ican/datasets/Cho2017')
    example = protocol['source_reference_example']
    person = load_subject(example['person'])
    index = example['original_order']
    original = read_json(HERE / 'cho2017_protocol.json')
    baseline, start, stop = _filtered_epoch(person.samples[index], person.cue_sample, original)
    raw_path = raw_root / f's{example["person"]:02d}.mat'
    eeg = loadmat(raw_path, squeeze_me=True, struct_as_record=False)['eeg']
    key = ['imagery_left','imagery_right'][int(person.labels[index])]
    class_index = int(person.class_trial_indices[index])
    all64 = getattr(eeg, key)[:64, class_index*3584:(class_index+1)*3584].T.astype(np.float64)
    selected = all64[:, list(PICKS)]
    np.testing.assert_array_equal(selected, person.samples[index])
    reference64 = all64 - all64.mean(axis=1, keepdims=True)
    # The existing helper re-references to eight-CAR; retain all64-CAR here.
    desired = reference64[:, list(PICKS)]
    desired = desired - desired[0]
    fir = 125 * signal.firwin(5121, 1/256, window=('kaiser',5))
    converted = signal.upfirdn(fir, desired, 125, 256, axis=0)[:1750]
    filtered = signal.sosfilt(signal.butter(4, [8,30], fs=250, btype='bandpass', output='sos'),
                              CausalEEGFilter().process(converted), axis=0)[start:stop].T
    current = baseline[2][start:stop].T
    result['reference_example'] = {'person': example['person'], 'original_order': index,
        'raw_mat_sha256': digest(raw_path), 'raw_dtype': str(getattr(eeg,key).dtype),
        'current_eight_car_std_mat_units': current.std(axis=1).tolist(),
        'all64_car_std_mat_units': filtered.std(axis=1).tolist(),
        'all64_over_eight_rms_ratio': float(np.linalg.norm(filtered)/np.linalg.norm(current)),
        'physical_unit_verified': False, 'unit_assumption': protocol['source_raw_unit_status']}
    capture = HERE / 'output/mi_live_capture_20261003/full_capture_audit'
    packets = np.fromfile(capture / 'packets.bin', dtype=PACKETS)
    raw = packets['adc'].astype(np.float64) * ADC_UV
    for row in diagnostic['live_diagnostics']:
        with np.load(capture/(row['trial_id']+'.npz'), allow_pickle=False) as data:
            waveform = data['filtered_uv'].copy()
            first, stop = int(data['window_start']), int(data['window_end_exclusive'])
        variants = []
        for warmup in protocol['live_filter_warmups_s']:
            start = first - round(warmup * 250)
            if start < 0:
                raise ValueError('Complete preceding filter warm-up required')
            segment = raw[start:stop]
            car = segment - segment.mean(axis=1, keepdims=True)
            conditioned = CausalEEGFilter().process(car)
            filtered = signal.sosfilt(signal.butter(4, [8,30], fs=250, btype='bandpass', output='sos'), conditioned, axis=0)
            counterfactual = filtered[-500:].T[None]
            logits = portable.logits(counterfactual)[0]
            variants.append({'warmup_s': warmup,
                'relative_waveform_rms_error': float(np.linalg.norm(counterfactual-waveform)/np.linalg.norm(waveform)),
                'max_error_uv': float(np.max(np.abs(counterfactual-waveform))),
                'logits': logits.tolist(), 'output': ['left','right'][int(logits.argmax())]})
        result['live_warmup_counterfactuals'].append({'trial_id': row['trial_id'], 'variants': variants})
    output.mkdir(parents=True)
    (output/'followup.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'output':str(output),'source_responses':result['source_amplitude_counterfactuals'],
                      'reference_ratio':result['reference_example']['all64_over_eight_rms_ratio']}),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
