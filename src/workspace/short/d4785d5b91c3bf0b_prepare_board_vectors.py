"""Generate synthetic, continuous-state Q16 golden frames; no board access."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from fixed_sos import FixedSOS, quantize

APP = HERE.parents[1]
SOS = APP / 'output/pl_primary_filter_q31_20260927/sos_float.npy'
COEFF = APP / 'output/pl_filter_v2025_2_20260927/coeff.hex'
MAGIC = b'GLDMA001'


def prepare(output, frames=300):
    if frames < 2 or frames > 10000:
        raise ValueError('Use 2..10000 frames')
    sos = np.load(SOS)
    model = FixedSOS(sos)
    encoded = [int(x, 16) for x in COEFF.read_text().split()]
    expected_coeff = [int(x) & ((1 << 34) - 1) for row in model.coeff for x in row]
    if encoded != expected_coeff:
        raise ValueError('Golden SOS does not match the candidate XPR coefficient file')
    # Distinct channels and samples exercise the last burst as well as channel order.
    t = np.arange(frames * 10) / 250.
    rng = np.random.default_rng(20260928)
    raw = np.stack([45*np.sin(2*np.pi*(7+c*.8)*t+c*.3) +
                    20*np.sin(2*np.pi*50*t) + 10*c +
                    rng.normal(0, 2, len(t)) for c in range(8)], axis=1)
    raw[250:260, 3] += np.linspace(0, 150, 10)
    packed = quantize(raw - raw[0], 16, 40)
    golden = model.process_quantized(packed)
    if model.saturations:
        raise ValueError('Non-clipping vectors required for the initial board gate')
    split_model = FixedSOS(sos)
    split = np.concatenate([split_model.process_quantized(packed[i:i+10])
                            for i in range(0, len(packed), 10)])
    np.testing.assert_array_equal(golden, split)
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'golden_frames.bin'
    payload = bytearray(struct.pack('<8sII', MAGIC, 1, frames))
    for tx, rx in zip(packed.reshape(-1, 80), golden.reshape(-1, 80)):
        payload.extend(struct.pack('<160q', *tx, *rx))
    target.write_bytes(payload)
    manifest = {
        'scope': 'synthetic bench vectors; not EEG accuracy or physical DDR evidence',
        'abi': 1, 'frames': frames, 'samples': len(raw), 'channels': 8,
        'channel_order': ['F3', 'F4', 'C3', 'C4', 'T7', 'T8', 'O1', 'O2'],
        'nominal_rate_hz': 250, 'data_bits': 40, 'data_frac': 16,
        'coefficient_bits': 34, 'coefficient_frac': 31,
        'rounding': 'nearest, exact halves away from zero',
        'initial_state': 'zero; one first-sample origin for the entire sequence',
        'saturations': model.saturations, 'comparison': 'all 80 words, bit-exact',
        'split_continuous_parity': True,
        'sha256': {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in (SOS, COEFF, HERE.parent / 'fixed_sos.py', target)},
    }
    (output / 'vectors_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'status': 'GOLDEN_VECTORS_PREPARED', 'frames': frames,
                      'file': str(target), 'sha256': hashlib.sha256(payload).hexdigest()}))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=300)
    args = parser.parse_args()
    prepare(args.output, args.frames)
