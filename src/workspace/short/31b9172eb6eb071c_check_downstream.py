"""Filter substitution risk check, not live-service or accuracy validation."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0,str(ROOT/'pynq_guardianloop'))
from cyton_sqi import CausalEEGFilter, CytonSQIMonitor
from cyton_covariance import CovarianceFeatureStream, CovarianceSVM
from cyton_fatigue import FourChannelDEStream
from fixed_sos import FixedSOS, quantize, DATA_BITS, DATA_FRAC


def compare(raw, model):
    floating = CausalEEGFilter().process(raw)
    fixed = FixedSOS(CausalEEGFilter().sos).process_quantized(
        quantize(raw-raw[0], DATA_FRAC, DATA_BITS))/(1 << DATA_FRAC)
    cap = ('F3','F4','C3','C4','T7','T8','O1','O2')
    streams = [CovarianceFeatureStream(cap) for _ in range(2)]
    fatigue = [FourChannelDEStream() for _ in range(2)]
    quality = [CytonSQIMonitor() for _ in range(2)]
    cov_errors, de_errors, score_errors = [], [], []
    decision_changes, gate_changes = [], []
    accepted_both = 0
    window_rows = []
    for start in range(0,len(raw)-249,250):
        end = start+250
        for index, values in enumerate((floating, fixed)):
            streams[index].append(values[start:end])
            fatigue[index].append(values[start:end])
        if end % 2000 == 0:
            q = [monitor.process(values[end-2000:end])
                 for monitor, values in zip(quality,(floating,fixed))]
            signature = lambda x:(x['state'],x['calibrated'],x['bad_channels'],
                                  [(c['calibrated'],c['usable']) for c in x['channels']])
            if signature(q[0]) != signature(q[1]):
                gate_changes.append(end)
            if all(all(row['quality'][i] >= .5 for i in (0,1,4,5,6,7)) for row in q):
                accepted_both += 1
            features = [s.features() for s in fatigue]
            de_errors.append(float(np.abs(features[0]-features[1]).max()))
            window_rows.append(dict(end_sample=end, float_bad=q[0]['bad_channels'],fixed_bad=q[1]['bad_channels']))
        if streams[0].ready and end % 500 == 0:
            features = [s.feature() for s in streams]
            cov_errors.append(float(np.abs(features[0]-features[1]).max()))
            # Un-gated scores are compared only as numerical diagnostics, never published as live labels.
            predictions = [model.predict_feature(f) for f in features]
            score_errors.append(float(np.abs(np.asarray(predictions[0][2])-predictions[1][2]).max()))
            if predictions[0][0] != predictions[1][0]:
                decision_changes.append(end)
    return dict(samples=len(raw), sqi_windows=len(window_rows),
                six_model_channels_quality_ok_both_windows=accepted_both,
                sqi_gate_changes_end_samples=gate_changes, cov_windows=len(cov_errors),
                max_cov_feature_abs_difference=max(cov_errors),
                max_de_feature_abs_difference=max(de_errors),
                max_svm_pair_score_abs_difference=max(score_errors),
                diagnostic_class_changes_end_samples=decision_changes, sqi_windows_detail=window_rows)


def main():
    out = ROOT/'eeg_apps_z15/output/pl_primary_filter_q31_20260927/downstream.json'
    if out.exists():
        raise FileExistsError(out)
    model_path = ROOT/'pynq_guardianloop/gameemo_covariance_svm.npz'
    model = CovarianceSVM(model_path)
    report = dict(scope='Offline arithmetic substitution only. No packet-gap state machine, no PL, no labels/accuracy. '
                       'SQI compared separately; classifier diagnostics include rejected windows and are NOT usable predictions.',
                  model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),cases={})
    for name, path, key in (
        ('bench_nonwear',ROOT/'eeg_apps_z15/output/accepted_bench_load_20260927/bench_input.npz','recorded'),
        ('cyton_recorded',ROOT/'eeg_apps_z15/output/seed_recorded_replay_20260926/input.npz','cyton')):
        with np.load(path) as z:
            report['cases'][name] = compare(z[key],model)
        print(name,json.dumps({k:v for k,v in report['cases'][name].items() if k!='sqi_windows_detail'}),flush=True)
    out.write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
