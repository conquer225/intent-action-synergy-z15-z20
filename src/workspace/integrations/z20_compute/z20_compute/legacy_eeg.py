"""Read-only adapters to the frozen Z15 EEG implementations and model baseline.

    Taps observe the vector passed to an existing classifier, so its filtering,
    calibration, causal mean update and EMA are not independently reimplemented.
"""
import importlib
from pathlib import Path
import sys
import numpy as np


class LegacyEEGFeatures:
    def __init__(self, legacy_directory=None):
        bundled = Path(__file__).resolve().parents[1]/"legacy"
        default = bundled if bundled.is_dir() else Path(__file__).resolve().parents[3]/"multimodal/vendor/runtime"
        self.directory = Path(legacy_directory) if legacy_directory else default
        self.directory = self.directory.resolve()
        required = ["cyton_fatigue.py", "cyton_sqi.py", "seed_shadow_policy.py",
                    "seed_shadow_weights.npz", "cyton_fatigue_overlap4.json"]
        if any(not (self.directory/name).is_file() for name in required):
            raise FileNotFoundError("complete original EEG runtime and baseline models required")
        if str(self.directory) not in sys.path:
            sys.path.insert(0, str(self.directory))
        modules = [importlib.import_module(name) for name in ("cyton_fatigue", "cyton_sqi", "seed_shadow_policy")]
        if any(Path(m.__file__).resolve().parent != self.directory for m in modules):
            raise RuntimeError("another EEG runtime has already been imported")
        self.fatigue_module, self.sqi_module, self.seed_module = modules
        self.reset()

    def reset(self):
        fatigue_parent, seed_parent = self.fatigue_module.FourChannelFatigue, self.seed_module.ShadowPolicy
        class FatigueTap(fatigue_parent):
            tapped = None
            def _predict(self, features):
                self.tapped = np.array(features, copy=True)
                return super()._predict(features)
        class SeedTap(seed_parent):
            def __init__(self, weights):
                self.tapped = []
                super().__init__(weights)
            def _accept_feature(self, features):
                centered = np.array(features-self.mean, copy=True)
                output = super()._accept_feature(features)
                if output["state"] == "prediction":
                    self.tapped.append((centered, output))
                return output
        self.fatigue = FatigueTap(self.directory/"cyton_fatigue_overlap4.json")
        with np.load(self.directory/"seed_shadow_weights.npz", allow_pickle=False) as data:
            self.emotion = SeedTap(dict(data))
        self.prefilter = self.sqi_module.CausalEEGFilter()
        self.sqi = self.sqi_module.CytonSQIMonitor(calibration_windows=15, sample_rate_hz=250)
        self.pending = np.empty((0, 8))
        self.fatigue_pending = []

    def feed(self, samples):
        samples = np.asarray(samples, dtype=np.float64)
        if samples.ndim != 2 or samples.shape[1] != 8 or not np.isfinite(samples).all():
            raise ValueError("raw 250Hz EEG in microvolts, fixed eight-channel order required")
        self.pending = np.concatenate((self.pending, samples))
        outputs = []
        while len(self.pending) >= 500:
            block, self.pending = self.pending[:500], self.pending[500:]
            self.emotion.tapped.clear()
            seed_events = self.emotion.feed_block(block)
            if self.emotion.tapped:
                for features, baseline in self.emotion.tapped:
                    outputs.append(dict(task="emotion", features=features, valid=True, state="ready", baseline=baseline))
            else:
                event = seed_events[-1]
                outputs.append(dict(task="emotion", features=None, valid=False, state=event["state"], baseline=event))
            filtered = self.prefilter.process(block)
            self.fatigue.append(filtered)
            self.fatigue_pending.append(filtered)
            if len(self.fatigue_pending) == 4:
                window = np.concatenate(self.fatigue_pending)
                self.fatigue_pending.clear()
                quality = self.sqi.process(window)
                quality_ok = all(quality["channels"][i]["quality"] >= .5 for i in (4, 5, 6, 7))
                self.fatigue.tapped = None
                baseline = self.fatigue.process_window(quality_ok, True)
                features = self.fatigue.tapped
                outputs.append(dict(task="fatigue", features=features, valid=features is not None,
                                    state="ready" if features is not None else baseline["state"], baseline=baseline))
        return outputs
