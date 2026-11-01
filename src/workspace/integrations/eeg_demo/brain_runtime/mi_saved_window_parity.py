"""Replay saved model windows only, not raw filtering or new wearer accuracy."""
import argparse
from pathlib import Path

import numpy as np
from mi_eegnet_rms import OfflineEEGNet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with np.load(args.input, allow_pickle=False) as data:
        logits = OfflineEEGNet(args.model, allow_experimental=True).logits(data['waveforms'])
        np.testing.assert_allclose(logits, data['logits'], rtol=0, atol=1e-5)
        np.testing.assert_array_equal(logits.argmax(1), data['logits'].argmax(1))
        error = float(np.max(np.abs(logits-data['logits'])))
        np.savez_compressed(args.output, logits=logits)
    print('SAVED_WINDOW_PARITY_PASS', len(logits), error)


if __name__ == '__main__':
    main()
