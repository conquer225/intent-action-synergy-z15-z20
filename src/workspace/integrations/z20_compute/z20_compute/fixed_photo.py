"""Three fixed photo templates encoded as weights for the existing INT8 MLP."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from .npu import QuantizedMLP


LABELS = ('person', 'dog', 'background')
PREPROCESSOR = 'rgb-gray32-centered-l2-int8-v1'


def _unit_pixels(image):
    pixels = np.asarray(image)
    if (pixels.dtype != np.uint8 or pixels.ndim not in (2, 3)
            or (pixels.ndim == 3 and pixels.shape[2] != 3)):
        raise ValueError('expected GRAY8 or RGB888 image')
    gray = Image.fromarray(pixels).convert('L').resize((32, 32), Image.Resampling.BOX)
    values = np.asarray(gray, dtype=np.float64).reshape(-1)
    values -= values.mean()
    length = np.linalg.norm(values)
    if length < 1e-6:
        raise ValueError('flat image has no template information')
    return values / length


@dataclass(frozen=True)
class PhotoPrediction:
    class_id: object
    scores: np.ndarray
    backend: str


class FixedPhotoMemory:
    def __init__(self, integer, gain):
        self.integer = integer
        self.gain = float(gain)
        if integer.w1.shape != (32, 1024) or not np.isfinite(self.gain) or self.gain <= 0:
            raise ValueError('invalid fixed-photo memory')

    @classmethod
    def remember(cls, images):
        if len(images) != 3:
            raise ValueError('one fixed photo for each of person, dog and background required')
        units = np.stack([_unit_pixels(image) for image in images])
        gain = min(1024., 126. / np.max(np.abs(units)))
        templates = np.rint(units * gain).astype(np.int8)
        maximum = np.max(np.sum(templates.astype(np.int64) ** 2, axis=1))
        shift = max(0, int(np.ceil(np.log2(maximum / 120.))))
        w1 = np.zeros((32, 1024), dtype=np.int8)
        w1[:3] = templates
        w2 = np.zeros((3, 32), dtype=np.int8)
        w2[:, :3] = np.eye(3, dtype=np.int8)
        integer = QuantizedMLP(w1, np.zeros(32, dtype=np.int32), w2,
                               np.zeros(3, dtype=np.int32), hidden_shift=shift)
        memory = cls(integer, gain)
        if [memory.predict(image).class_id for image in images] != [0, 1, 2]:
            raise ValueError('integer memory cannot distinguish these three templates')
        return memory

    def predict(self, image, *, backend=None):
        values = np.clip(np.rint(_unit_pixels(image) * self.gain), -127, 127).astype(np.int8)
        raw = self.integer.infer(values) if backend is None else backend.infer(self.integer, values)
        raw = np.asarray(raw)
        if raw.shape != (3,) or raw.dtype != np.int32:
            raise ValueError('NPU must return three INT32 scores')
        winners = np.flatnonzero(raw == raw.max())
        class_id = int(winners[0]) if len(winners) == 1 else None
        return PhotoPrediction(class_id, raw.copy(), 'PS_integer_reference' if backend is None else backend.name)

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / 'weights.npz'
        model = self.integer
        np.savez_compressed(path, w1=model.w1, b1=model.b1, w2=model.w2, b2=model.b2)
        metadata = dict(format='z20-fixed-photo-v1', preprocessor=PREPROCESSOR,
                        labels=LABELS, gain=self.gain, hidden_shift=model.hidden_shift,
                        method='prototype weights', evaluation_scope='same three registered photos',
                        weights_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        (directory / 'model.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')

    @classmethod
    def load(cls, directory):
        directory = Path(directory)
        metadata = json.loads((directory / 'model.json').read_text(encoding='utf-8'))
        path = directory / 'weights.npz'
        if (metadata.get('format') != 'z20-fixed-photo-v1'
                or metadata.get('preprocessor') != PREPROCESSOR
                or tuple(metadata.get('labels', ())) != LABELS
                or hashlib.sha256(path.read_bytes()).hexdigest() != metadata['weights_sha256']):
            raise ValueError('fixed-photo artifact contract or hash mismatch')
        with np.load(path, allow_pickle=False) as weights:
            integer = QuantizedMLP(weights['w1'], weights['b1'], weights['w2'], weights['b2'],
                                   hidden_shift=metadata['hidden_shift'])
        return cls(integer, metadata['gain'])
