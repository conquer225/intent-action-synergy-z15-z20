"""Fixed three-scene memory for the shared INT8 NPU, with reviewed annotations."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np

from .npu import QuantizedMLP
from .fixed_scene_depth import estimate_geometry


PREPROCESSOR = 'rgb640x480-gray32-blockmean-centered-l2-int8-v1'
INTERACTIONS = ('holding', 'petting', 'leashing', 'walking_with_dog')


def _unit_pixels(image):
    image = np.asarray(image)
    if image.shape != (480, 640, 3) or image.dtype != np.uint8:
        raise ValueError('expected 640x480 RGB888 pixels')
    rgb = image.astype(np.uint32)
    gray = (77 * rgb[:, :, 0] + 150 * rgb[:, :, 1] + 29 * rgb[:, :, 2] + 128) >> 8
    values = gray.reshape(32, 15, 32, 20).mean(axis=(1, 3)).reshape(-1)
    values -= values.mean()
    length = np.linalg.norm(values)
    if length < 1e-6:
        return None
    return values / length


@dataclass(frozen=True)
class ScenePrediction:
    scene_id: object
    scores: np.ndarray
    backend: str


class FixedSceneMemory:
    """Pixel input -> scene ID; the optional backend has infer(model, int8[D])."""
    def __init__(self, integer, gain, minimum_score=40, minimum_margin=16):
        self.integer = integer
        self.gain = float(gain)
        self.minimum_score = int(minimum_score)
        self.minimum_margin = int(minimum_margin)
        if (integer.w1.shape != (32, 1024) or not np.isfinite(self.gain)
                or self.gain <= 0 or self.minimum_score < 0 or self.minimum_margin < 0):
            raise ValueError('invalid fixed-scene memory')

    @classmethod
    def remember(cls, images):
        if len(images) != 3:
            raise ValueError('exactly three registered scenes required')
        units = [_unit_pixels(image) for image in images]
        if any(unit is None for unit in units):
            raise ValueError('flat scene cannot be registered')
        units = np.stack(units)
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
        if [memory.recognize(image).scene_id for image in images] != [0, 1, 2]:
            raise ValueError('integer memory cannot distinguish registered scenes')
        return memory

    def recognize(self, image, *, backend=None):
        unit = _unit_pixels(image)
        name = 'PS_integer_reference' if backend is None else backend.name
        if unit is None:
            return ScenePrediction(None, np.zeros(3, dtype=np.int32), name)
        values = np.clip(np.rint(unit * self.gain), -127, 127).astype(np.int8)
        scores = self.integer.infer(values) if backend is None else backend.infer(self.integer, values)
        scores = np.asarray(scores)
        if scores.shape != (3,) or scores.dtype != np.int32:
            raise ValueError('NPU must return three INT32 scores')
        order = np.argsort(scores)
        best, second = int(order[-1]), int(order[-2])
        scene_id = best if (scores[best] >= self.minimum_score
                            and scores[best] - scores[second] >= self.minimum_margin) else None
        return ScenePrediction(scene_id, scores.copy(), name)

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / 'weights.npz'
        model = self.integer
        np.savez_compressed(path, w1=model.w1, b1=model.b1, w2=model.w2, b2=model.b2)
        metadata = dict(format='z20-fixed-scene-v1', preprocessor=PREPROCESSOR,
                        gain=self.gain, hidden_shift=model.hidden_shift,
                        minimum_score=self.minimum_score, minimum_margin=self.minimum_margin,
                        evaluation_scope='same three registered scenes',
                        weights_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        (directory / 'model.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')

    @classmethod
    def load(cls, directory):
        directory = Path(directory)
        metadata = json.loads((directory / 'model.json').read_text(encoding='utf-8'))
        path = directory / 'weights.npz'
        if (metadata.get('format') != 'z20-fixed-scene-v1'
                or metadata.get('preprocessor') != PREPROCESSOR
                or hashlib.sha256(path.read_bytes()).hexdigest() != metadata['weights_sha256']):
            raise ValueError('fixed-scene artifact contract or hash mismatch')
        with np.load(path, allow_pickle=False) as weights:
            model = QuantizedMLP(weights['w1'], weights['b1'], weights['w2'], weights['b2'],
                                 hidden_shift=metadata['hidden_shift'])
        return cls(model, metadata['gain'], metadata['minimum_score'], metadata['minimum_margin'])


def describe_scene(annotation, size):
    if tuple(size) != (640, 480) or annotation.get('interaction') not in INTERACTIONS:
        raise ValueError('expected reviewed 640x480 person-dog interaction')
    boxes = {}
    for label in ('person', 'dog'):
        box = annotation.get(label)
        if (not isinstance(box, (list, tuple)) or len(box) != 4
                or any(type(v) is not int for v in box)
                or not (0 <= box[0] < box[2] <= 640 and 0 <= box[1] < box[3] <= 480)):
            raise ValueError('invalid ' + label + ' box')
        boxes[label] = list(box)
    person_x = boxes['person'][0] + boxes['person'][2]
    dog_x = boxes['dog'][0] + boxes['dog'][2]
    position = ('person_left_of_dog' if person_x < dog_x else
                'person_right_of_dog' if person_x > dog_x else 'same_horizontal_position')
    return dict(boxes=boxes, position=position, interaction=annotation['interaction'],
                geometry=estimate_geometry(annotation, size))
