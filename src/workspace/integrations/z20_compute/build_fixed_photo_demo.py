"""Recreate memory weights and previews from the three already-downloaded photos."""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from z20_compute.fixed_photo import FixedPhotoMemory
from z20_compute.fixed_photo_demo import PhotoDemo, export


def main():
    here = Path(__file__).resolve().parent
    root = here / 'artifacts' / 'fixed_photo_demo'
    files = json.loads((root / 'gallery.json').read_text(encoding='utf-8'))['images']
    images = []
    for filename in files:
        with Image.open(root / filename) as source:
            images.append(np.asarray(ImageOps.exif_transpose(source).convert('RGB')))
    FixedPhotoMemory.remember(images).save(root / 'model')
    report = export(PhotoDemo(root), here / 'report' / 'fixed_photo_demo')
    if [item['class_id'] for item in report['results']] != [0, 1, 2]:
        raise RuntimeError('fixed photo recall failed')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
