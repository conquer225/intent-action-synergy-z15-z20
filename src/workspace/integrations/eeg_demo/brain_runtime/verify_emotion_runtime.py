"""Check named-channel mapping, gates and PC/ARM numerical agreement."""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from cyton_sqi import GameemoEmotionRecognizer

CHANNELS = ("F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    args = parser.parse_args()
    model = GameemoEmotionRecognizer(args.model)
    samples = np.load(args.fixture)["samples_uv"]
    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    predict = lambda values, q, names=CHANNELS: model.predict(values, q, source_channel_map=names)
    base = predict(samples, np.ones(8))
    assert base["class_id"] == expected["class_id"]
    np.testing.assert_allclose(list(base["probabilities"].values()),
                               list(expected["probabilities"].values()), atol=1e-4, rtol=0)
    reordered = predict(samples[:, ::-1], np.ones(8), CHANNELS[::-1])
    assert reordered["probabilities"] == base["probabilities"]
    unused_changed = samples.copy()
    unused_changed[:, 2:4] = 100000
    assert predict(unused_changed, np.ones(8))["probabilities"] == base["probabilities"]
    quality = np.ones(8)
    quality[0] = 0
    assert predict(samples, quality)["valid"]
    quality[1] = 0
    assert not predict(samples, quality)["valid"]
    try:
        predict(samples, np.ones(8), ("AF3",) + CHANNELS[1:])
    except ValueError:
        pass
    else:
        raise AssertionError("missing model channel was accepted")
    latencies = []
    for _ in range(20):
        started = time.perf_counter()
        predict(samples, np.ones(8))
        latencies.append(1000 * (time.perf_counter() - started))
    print(json.dumps({"passed": True, "model_channels": model.channels,
                      "pc_arm_probability_max_error": float(np.max(np.abs(
                          np.asarray(list(base["probabilities"].values())) -
                          np.asarray(list(expected["probabilities"].values()))))),
                      "mapping_permutation": "passed", "unused_C3_C4": "passed",
                      "five_of_six_gate": "passed", "missing_channel_rejection": "passed",
                      "inference_ms_median": float(np.median(latencies)),
                      "inference_ms_p95": float(np.percentile(latencies, 95)),
                      "repetitions": len(latencies)}))


if __name__ == "__main__":
    main()
