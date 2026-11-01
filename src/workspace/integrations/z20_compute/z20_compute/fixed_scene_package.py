"""Integrity-checked raw scene bundle shared by the desktop builder and ARM runner."""
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np

from .fixed_scene import FixedSceneMemory, describe_scene


INPUT_BYTES = 640 * 480 * 3
FRAME_BYTES = 1280 * 720 * 3


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_package(gallery_root, output):
    """PC-only build: PNG/JPEG -> raw RGB plus three pre-rendered HDMI frames."""
    from PIL import Image
    from .fixed_scene_demo import SceneDemo, render

    gallery_root, output = Path(gallery_root), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    gallery = json.loads((gallery_root / 'gallery.json').read_text(encoding='utf-8'))
    sources = json.loads((gallery_root / 'sources.json').read_text(encoding='utf-8'))
    if gallery.get('format') != 'z20-person-dog-gallery-v1' or len(gallery['images']) != 3:
        raise ValueError('expected reviewed three-scene gallery')
    if len(sources) != 3:
        raise ValueError('expected three source records')
    demo = SceneDemo(gallery_root)
    files = ['gallery.json', 'sources.json', 'model/model.json', 'model/weights.npz']
    shutil.copyfile(gallery_root / 'gallery.json', output / 'gallery.json')
    shutil.copyfile(gallery_root / 'sources.json', output / 'sources.json')
    (output / 'model').mkdir(exist_ok=True)
    for name in ('model.json', 'weights.npz'):
        shutil.copyfile(gallery_root / 'model' / name, output / 'model' / name)
    for index, entry in enumerate(gallery['images']):
        if (sources[index]['scene'] != index or sources[index]['original'] != entry['original']
                or _digest(gallery_root / entry['original']) != sources[index]['sha256']):
            raise ValueError('source image provenance or hash mismatch')
        with Image.open(gallery_root / entry['file']) as source:
            pixels = source.convert('RGB')
        describe_scene(entry, pixels.size)
        if pixels.size != (640, 480):
            raise ValueError('scene image must be 640x480')
        input_name = 'input_{}.rgb'.format(index)
        display_name = 'display_{}.rgb'.format(index)
        (output / input_name).write_bytes(pixels.tobytes())
        demo.index = index
        (output / display_name).write_bytes(render(demo, board_controls=True).tobytes())
        files.extend((input_name, display_name))
    manifest = dict(format='z20-person-dog-board-v1', input_size=[640, 480],
                    display_size=[1280, 720], pixel_order='RGB888',
                    scope='three registered photographs',
                    files={name: _digest(output / name) for name in files})
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


class BoardSceneBundle:
    def __init__(self, directory, backend=None):
        self.directory = Path(directory)
        manifest = json.loads((self.directory / 'manifest.json').read_text(encoding='utf-8'))
        expected = {'gallery.json', 'sources.json', 'model/model.json', 'model/weights.npz'}
        expected.update('input_{}.rgb'.format(i) for i in range(3))
        expected.update('display_{}.rgb'.format(i) for i in range(3))
        if (manifest.get('format') != 'z20-person-dog-board-v1'
                or manifest.get('input_size') != [640, 480]
                or manifest.get('display_size') != [1280, 720]
                or manifest.get('pixel_order') != 'RGB888'
                or set(manifest.get('files', {})) != expected):
            raise ValueError('board bundle contract mismatch')
        for name, digest in manifest['files'].items():
            if _digest(self.directory / name) != digest:
                raise ValueError('board bundle hash mismatch: ' + name)
        for i in range(3):
            if ((self.directory / ('input_{}.rgb'.format(i))).stat().st_size != INPUT_BYTES
                    or (self.directory / ('display_{}.rgb'.format(i))).stat().st_size != FRAME_BYTES):
                raise ValueError('board bundle raw frame size mismatch')
        self.entries = json.loads((self.directory / 'gallery.json').read_text(encoding='utf-8'))['images']
        if len(self.entries) != 3:
            raise ValueError('board bundle must have three annotations')
        self.memory = FixedSceneMemory.load(self.directory / 'model')
        self.backend = backend

    def evaluate(self, input_index):
        if type(input_index) is not int or not 0 <= input_index < 3:
            raise ValueError('input index outside gallery')
        raw = (self.directory / ('input_{}.rgb'.format(input_index))).read_bytes()
        image = np.frombuffer(raw, dtype=np.uint8).reshape(480, 640, 3)
        prediction = self.memory.recognize(image, backend=self.backend)
        if self.backend is not None:
            reference = self.memory.recognize(image)
            if not np.array_equal(prediction.scores, reference.scores):
                raise ValueError('PL/PS integer scores differ for selected scene')
        scene = (None if prediction.scene_id is None else
                 describe_scene(self.entries[prediction.scene_id], (640, 480)))
        return dict(input_index=input_index, scene_id=prediction.scene_id,
                    scores=prediction.scores.tolist(), backend=prediction.backend,
                    position=None if scene is None else scene['position'],
                    interaction=None if scene is None else scene['interaction'],
                    boxes=None if scene is None else scene['boxes'],
                    geometry=None if scene is None else scene['geometry'],
                    display=None if scene is None else 'display_{}.rgb'.format(prediction.scene_id))
