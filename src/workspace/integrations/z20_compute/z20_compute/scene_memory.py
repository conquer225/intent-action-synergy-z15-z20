"""Known person/dog scenes: pure NumPy preprocessing and the shared INT8 NPU."""
import json
from pathlib import Path

import numpy as np

from .npu import QuantizedMLP


def unit_pixels(rgb):
    rgb = np.asarray(rgb)
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 1:
        raise ValueError('expected nonempty RGB888 image')
    h, w = rgb.shape[:2]
    rows = (np.arange(32) * 2 + 1) * h // 64
    cols = (np.arange(32) * 2 + 1) * w // 64
    sampled = rgb[rows[:, None], cols[None, :]].astype(np.uint32)
    gray = ((77 * sampled[:, :, 0] + 150 * sampled[:, :, 1] + 29 * sampled[:, :, 2] + 128) >> 8)
    values = gray.astype(np.float64).reshape(-1)
    values -= values.mean()
    length = np.sqrt(np.sum(values * values))
    if length < 1e-6:
        raise ValueError('flat input')
    return values / length


def horizontal_relation(person, dog):
    delta = (dog[0] + dog[2] - person[0] - person[2]) / 2.
    return 'dog_left_of_person' if delta < -2 else 'dog_right_of_person' if delta > 2 else 'horizontal_overlap'


class TemplateMemory:
    def __init__(self, integer, gain):
        self.integer, self.gain = integer, float(gain)

    @classmethod
    def remember(cls, units):
        units = np.asarray(units, dtype=np.float64)
        if units.shape != (3, 1024) or not np.isfinite(units).all() or np.max(np.abs(units)) == 0:
            raise ValueError('three finite 1024-element templates required')
        gain = min(1024., 126. / np.max(np.abs(units)))
        templates = np.rint(units * gain).astype(np.int8)
        maximum = np.max(np.sum(templates.astype(np.int64) ** 2, axis=1))
        shift = max(0, int(np.ceil(np.log2(maximum / 120.))))
        w1, w2 = np.zeros((32, 1024), np.int8), np.zeros((3, 32), np.int8)
        w1[:3], w2[:, :3] = templates, np.eye(3, dtype=np.int8)
        memory = cls(QuantizedMLP(w1, np.zeros(32, np.int32), w2, np.zeros(3, np.int32), hidden_shift=shift), gain)
        if [int(np.argmax(memory.scores(row))) for row in units] != [0, 1, 2]:
            raise ValueError('templates cannot be distinguished after quantization')
        return memory

    def input_values(self, unit):
        return np.clip(np.rint(unit * self.gain), -127, 127).astype(np.int8)

    def scores(self, unit, backend=None):
        values = self.input_values(unit)
        output = self.integer.infer(values) if backend is None else backend.infer(self.integer, values)
        output = np.asarray(output)
        if output.shape != (3,) or output.dtype != np.int32:
            raise ValueError('NPU returned invalid output')
        return output

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        m = self.integer
        np.savez_compressed(path, w1=m.w1, b1=m.b1, w2=m.w2, b2=m.b2,
                            hidden_shift=np.array(m.hidden_shift), gain=np.array(self.gain))

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as a:
            m = QuantizedMLP(a['w1'], a['b1'], a['w2'], a['b2'], hidden_shift=int(a['hidden_shift']))
            return cls(m, float(a['gain']))


class SceneRecognizer:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.config = json.loads((self.directory / 'scenes.json').read_text(encoding='utf-8'))
        self.memory = TemplateMemory.load(self.directory / 'scene.npz')

    def infer(self, rgb, *, backend=None):
        backend_name = 'PS_integer_reference' if backend is None else backend.name
        result = dict(valid=False, scene_id=None, objects=[], relations=[], scores=[],
                      backend=backend_name, scope='registered scenes only',
                      localization='registered boxes verified by crop classification',
                      interaction_source='registered scene memory')
        try:
            scores = self.memory.scores(unit_pixels(rgb), backend)
        except ValueError as exc:
            if str(exc) != 'flat input':
                raise
            result['state'] = 'uninformative_input'
            return result
        ordered = np.sort(scores)
        result['scores'] = scores.tolist()
        if scores.max() < self.config['minimum_score'] or ordered[-1] - ordered[-2] < self.config['minimum_margin']:
            result['state'] = 'unknown_scene'
            return result
        scene_id = int(np.argmax(scores))
        scene = self.config['scenes'][scene_id]
        if list(rgb.shape) != scene['shape']:
            result['state'] = 'input_geometry_mismatch'
            return result
        objects = TemplateMemory.load(self.directory / scene['object_model'])
        nodes = []
        for expected, label in enumerate(('person', 'dog', 'background')):
            x0, y0, x1, y1 = scene['boxes'][label]
            crop = rgb[y0:y1, x0:x1]
            scores = objects.scores(unit_pixels(crop), backend)
            if int(np.argmax(scores)) != expected or np.sum(scores == scores.max()) != 1:
                result['state'] = 'object_crop_mismatch'
                return result
            if expected < 2:
                nodes.append(dict(id=label, label=label, box=[x0, y0, x1, y1], scores=scores.tolist()))
        result.update(valid=True, scene_id=scene_id, state='recognized', objects=nodes,
                      relations=[dict(subject='person', predicate=scene['interaction'], object='dog'),
                                 dict(subject='dog', predicate=horizontal_relation(scene['boxes']['person'], scene['boxes']['dog']), object='person')])
        return result
