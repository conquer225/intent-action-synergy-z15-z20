"""Boot-local calibration only: no raw EEG, predictions, or filter history."""
import hashlib
import json
import os
from pathlib import Path
import stat

import numpy as np


class CalibrationSession:
    def __init__(self, path, context):
        self.path = Path(path)
        self.context = context
        self.last_progress = None

    @staticmethod
    def context_for(port, channels, microvolts_per_count, model_paths, backend):
        return dict(boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                    serial_identity=port, channels=list(channels),
                    microvolts_per_count=microvolts_per_count, filter_backend=backend,
                    models={Path(p).name: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                            for p in model_paths if Path(p).is_file()},
                    filter_contract='cyton-causal-1-45Hz-notch50-v1')

    def save(self, sqi, fatigue):
        progress = tuple(len(r) for r in sqi.reference) + (len(fatigue.baseline) if fatigue else 0,)
        if progress == self.last_progress or not any(progress):
            return False
        row = dict(format='guardianloop-boot-calibration-v1', context=self.context,
                   sqi=dict(reference=[np.asarray(r).tolist() for r in sqi.reference],
                            center=sqi.center.tolist(), scale=sqi.scale.tolist(),
                            threshold=sqi.threshold.tolist(),
                            calibrated_channels=sqi.calibrated_channels.tolist()),
                   fatigue=None if fatigue is None else dict(
                       baseline=[v.tolist() for v in fatigue.baseline],
                       mean=None if fatigue.mean is None else fatigue.mean.tolist(),
                       scale=None if fatigue.scale is None else fatigue.scale.tolist()))
        encoded = json.dumps(row, allow_nan=False).encode()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + '.part')
        with open(temporary, 'wb') as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(encoded)
        temporary.replace(self.path)
        self.last_progress = progress
        return True

    def load(self, sqi, fatigue):
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return False
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_size > 512_000):
            raise ValueError('Calibration checkpoint ownership, mode, or size mismatch')
        row = json.loads(self.path.read_text())
        if not isinstance(row, dict):
            raise ValueError('Invalid calibration checkpoint object')
        if row.get('format') != 'guardianloop-boot-calibration-v1' or row.get('context') != self.context:
            return False

        def array(value, shape):
            a = np.asarray(value, dtype=float)
            if a.shape != shape or not np.isfinite(a).all():
                raise ValueError('Invalid calibration array')
            return a

        saved = row['sqi']
        flags = saved['calibrated_channels']
        if len(flags) != 8 or any(type(v) is not bool for v in flags):
            raise ValueError('Invalid SQI calibration flags')
        references = saved['reference']
        if len(references) != 8:
            raise ValueError('Invalid SQI channel count')
        limit = sqi.calibration_windows * (2000 // sqi.segment_samples)
        validated = []
        for reference, ready in zip(references, flags):
            if len(reference) > limit or ready != (len(reference) == limit):
                raise ValueError('Invalid SQI reference length')
            validated.append([] if not reference else list(array(reference, (len(reference), 7))))
        center = array(saved['center'], (8, 7))
        scale = array(saved['scale'], (8, 7))
        threshold = array(saved['threshold'], (8,))
        if np.any(scale <= 0) or np.any(threshold <= 0):
            raise ValueError('Invalid SQI calibration scale')
        baseline = mean = fatigue_scale = None
        if fatigue is not None:
            f = row['fatigue']
            total = int(fatigue.model['calibration_windows'])
            count = len(f['baseline'])
            features = 4 * len(fatigue.stream.sos)
            if not 0 <= count <= total:
                raise ValueError('Invalid fatigue baseline length')
            baseline = [] if not count else list(array(f['baseline'], (count, features)))
            if count == total:
                mean = array(f['mean'], (features,))
                fatigue_scale = array(f['scale'], (features,))
                if np.any(fatigue_scale <= 0):
                    raise ValueError('Invalid fatigue calibration scale')
            elif f['mean'] is not None or f['scale'] is not None:
                raise ValueError('Incomplete fatigue calibration marked complete')
        elif row['fatigue'] is not None:
            raise ValueError('Checkpoint belongs to a different fatigue engine')
        # Commit only after every array has passed. Never restore EMA or a result.
        sqi.reference = validated
        sqi.center, sqi.scale, sqi.threshold = center, scale, threshold
        sqi.calibrated_channels = np.asarray(flags, dtype=bool)
        if fatigue is not None:
            fatigue.baseline, fatigue.mean, fatigue.scale = baseline, mean, fatigue_scale
            fatigue.reset_stream()
        self.last_progress = tuple(len(r) for r in validated) + (len(baseline) if baseline is not None else 0,)
        return True
