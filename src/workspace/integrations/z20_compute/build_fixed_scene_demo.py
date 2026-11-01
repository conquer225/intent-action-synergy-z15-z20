"""Register the three reviewed photographs and export desktop/HDMI previews."""
import json
from pathlib import Path

import numpy as np
from PIL import Image

from z20_compute.fixed_scene import FixedSceneMemory, describe_scene
from z20_compute.fixed_scene_demo import SceneDemo, export


def main():
    here = Path(__file__).resolve().parent
    root = here / 'artifacts' / 'person_dog'
    gallery = json.loads((root / 'gallery.json').read_text(encoding='utf-8'))
    images = []
    for entry in gallery['images']:
        with Image.open(root / entry['file']) as source:
            image = np.asarray(source.convert('RGB'))
        describe_scene(entry, (image.shape[1], image.shape[0]))
        images.append(image)
    FixedSceneMemory.remember(images).save(root / 'model')
    report = export(SceneDemo(root), here / 'report' / 'person_dog')
    if [item['scene_id'] for item in report['results']] != [0, 1, 2]:
        raise RuntimeError('registered scene recall failed')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
