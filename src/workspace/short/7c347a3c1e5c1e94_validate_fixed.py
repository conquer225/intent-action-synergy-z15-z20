"""Numerical qualification and RTL vectors for the current primary prefilter."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.signal import sosfilt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'pynq_guardianloop'))
from cyton_sqi import CausalEEGFilter
from fixed_sos import FixedSOS, quantize, DATA_BITS, DATA_FRAC, COEFF_FRAC, COEFF_BITS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--coeff-bits', type=int, default=COEFF_BITS)
    parser.add_argument('--coeff-frac', type=int, default=COEFF_FRAC)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    # Engineering tolerances, not classifier accuracy or equivalence guarantees.
    protocol = dict(max_abs_error_uv=.05, rms_error_uv=.01,
                    saturations_on_recorded_and_normal_cases=0,
                    rtl_bit_exact=True, input_fraction_bits=DATA_FRAC,
                    data_bits=DATA_BITS, coeff_bits=args.coeff_bits, coeff_fraction_bits=args.coeff_frac,
                    cap=['F3','F4','C3','C4','T7','T8','O1','O2'],
                    filter='250 Hz; notch 50 Hz Q5; order-4 Butterworth bandpass 1–45 Hz',
                    includes_inference=False, changes_live_service=False)
    (out/'protocol.json').write_text(json.dumps(protocol, indent=2), encoding='utf-8')
    sos = CausalEEGFilter().sos
    def make_model():
        return FixedSOS(sos, coeff_bits=args.coeff_bits, coeff_frac=args.coeff_frac)
    model = make_model()
    np.save(out/'sos_float.npy', sos)
    np.savetxt(out/'coeff.hex', np.asarray(model.coeff).reshape(-1) & ((1<<args.coeff_bits)-1), fmt='%09x')
    q_sos = sos.copy()
    q_sos[:, [0,1,2,4,5]] = np.asarray(model.coeff)/(1 << args.coeff_frac)
    poles = [float(np.abs(np.roots(row[3:])).max()) for row in q_sos]
    rng = np.random.default_rng(20260927)
    t = np.arange(5000)/250
    clean = np.stack([30*np.sin(2*np.pi*(7+i)*t+i*.3) + 5*rng.normal(size=len(t))
                      for i in range(8)], axis=1)
    interference = clean + 1300*np.sin(2*np.pi*50*t)[:,None]
    pop = clean.copy()
    pop[1250:2500] += 15000
    impulse = np.zeros_like(clean)
    impulse[5] = 1000
    full_range = np.tile((187500*np.where(np.arange(5000)%2, 1., -1.))[:,None], (1,8))
    sources = {
        'bench': ROOT/'eeg_apps_z15/output/accepted_bench_load_20260927/bench_input.npz',
        'recorded': ROOT/'eeg_apps_z15/output/seed_recorded_replay_20260926/input.npz',
    }
    cases = {'clean':clean, 'mains_1300uv':interference, 'pop_15000uv':pop,
             'impulse':impulse, 'zero':np.zeros_like(clean), 'adc_full_range':full_range}
    with np.load(sources['bench']) as z:
        cases['bench_20260920_nonwear'] = z['recorded']
    with np.load(sources['recorded']) as z:
        cases['cyton_20260923_recorded'] = z['cyton']
    results = {}
    vector_count = 0
    # Each case resets; first raw sample is subtracted by ARM before quantization.
    with (out/'vectors.txt').open('w', encoding='ascii') as vectors:
        for name, raw in cases.items():
            centered = raw - raw[0]
            xq = quantize(centered, DATA_FRAC, DATA_BITS)
            model = make_model()
            yq = model.process_quantized(xq)
            golden = CausalEEGFilter().process(raw)
            quantized_input_golden = sosfilt(sos, xq/(1 << DATA_FRAC), axis=0)
            err = yq/(1 << DATA_FRAC) - golden
            # Batch partition must not reset states.
            split = make_model()
            parts = [split.process_quantized(xq[i:i+137]) for i in range(0,len(xq),137)]
            chunk_exact = np.array_equal(np.concatenate(parts), yq)
            metrics = dict(samples=len(raw), max_abs_error_uv=float(np.abs(err).max()),
                           rms_error_uv=float(np.sqrt(np.mean(err**2))),
                           quantized_input_only_max_error_uv=float(np.abs(quantized_input_golden-golden).max()),
                           saturations=model.saturations, max_acc_bits=model.max_acc_abs.bit_length()+1,
                           chunk_exact=chunk_exact)
            metrics['passed'] = (metrics['max_abs_error_uv'] <= protocol['max_abs_error_uv'] and
                                 metrics['rms_error_uv'] <= protocol['rms_error_uv'] and
                                 metrics['saturations'] == 0 and chunk_exact)
            results[name] = metrics
            print(name, json.dumps(metrics), flush=True)
            # Include full pop transition and recorded prefixes; exact fixed-point RTL test.
            count = min(len(xq), 3000 if name == 'pop_15000uv' else 1024)
            for i in range(count):
                for channel in range(8):
                    vectors.write(f'{int(i==0 and channel==0)} {channel} '
                                  f'{int(xq[i,channel]) & ((1<<DATA_BITS)-1):010x} '
                                  f'{int(yq[i,channel]) & ((1<<DATA_BITS)-1):010x}\n')
                    vector_count += 1
        # Deliberate overrange internal transient must saturate visibly, never wrap.
        extreme = np.tile(np.array([0, (1 << (DATA_BITS-1))-1, -(1 << (DATA_BITS-1))]*16,
                                   dtype=np.int64)[:,None], (1,8))
        sat = make_model()
        sat_y = sat.process_quantized(extreme)
        for i in range(len(extreme)):
            for channel in range(8):
                vectors.write(f'{int(i==0 and channel==0)} {channel} '
                              f'{int(extreme[i,channel]) & ((1<<DATA_BITS)-1):010x} '
                              f'{int(sat_y[i,channel]) & ((1<<DATA_BITS)-1):010x}\n')
                vector_count += 1
    report = dict(protocol=protocol, cases=results, quantized_pole_radii=poles,
                  coefficients_stable=all(p < 1 for p in poles),
                  rtl_vector_words=vector_count, saturation_stress_count=sat.saturations,
                  sources={key:dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                           for key,path in sources.items()},
                  passed=all(row['passed'] for row in results.values()) and all(p < 1 for p in poles),
                  scope='Numerical primary filter prototype only; no PL timing/resources or inference accuracy')
    (out/'numerical.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('NUMERICAL_PASS',report['passed'],flush=True)
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
