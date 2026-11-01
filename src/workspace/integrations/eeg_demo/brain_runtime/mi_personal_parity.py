"""Deterministic component parity probes, not a wearer accuracy experiment."""
import argparse
from pathlib import Path
import numpy as np
from mi_eegnet_rms import OfflineEEGNet
from mi_eegnet_frozen_rms import OfflineEEGNet as FrozenEEGNet
from mi_personal_study import PersonalReadout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    new = OfflineEEGNet('experimental_rms_eegnet.npz', allow_experimental=True)
    old = FrozenEEGNet('experimental_rms_eegnet.npz', allow_experimental=True)
    rng = np.random.default_rng(20261003)
    waves = rng.normal(size=(16, 8, 500)) * np.geomspace(.1, 100, 16)[:, None, None]
    features = new.features(waves)
    logits = new.score_features(features)
    np.testing.assert_allclose(logits, old.logits(waves), rtol=0, atol=1e-12)
    personal = PersonalReadout()
    personal.fit(features[:12], [-1, 1]*6)
    personal_logits = personal.logits(features[12:])
    np.savez_compressed(args.output, features=features, logits=logits,
                        personal_logits=personal_logits, **personal.arrays())
    print('FEATURE_REFACTOR_PARITY_PASSED; synthetic probes, not accuracy')


if __name__ == '__main__':
    main()
