"""Read-only render profiling with existing JPEG data; never opens display or USB."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from guide_render import Renderer
from media_menu import MenuView


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jpeg', type=Path, required=True)
    args = parser.parse_args()
    with Image.open(args.jpeg) as source:
        picture = source.convert('RGB')
    renderer = Renderer(local_media=True)
    view = MenuView(phase='video', title='正在观看', footer='无声视频 · 播放中暂停眼控 · PS_KEY1 退出',
                    video_frame=0, video_image=picture)
    renderer.render(view)
    stages = {name: [] for name in ('shell_copy', 'resize', 'raw_bgr', 'blit', 'render')}
    stages['numpy_nearest'] = []
    nearest = getattr(Image, 'Resampling', Image).NEAREST
    # Use this Pillow build's actual rounding, not a guessed nearest formula.
    x = np.asarray(Image.fromarray(np.arange(picture.width, dtype=np.int32)[None, :])
                   .resize((960, 1), nearest)).ravel().astype(np.intp)
    y = np.asarray(Image.fromarray(np.arange(picture.height, dtype=np.int32)[:, None])
                   .resize((1, 540), nearest)).ravel().astype(np.intp)
    for _ in range(12):
        started = time.perf_counter()
        frame = renderer.video_shell.copy()
        stages['shell_copy'].append(time.perf_counter() - started)
        started = time.perf_counter()
        resized = picture.resize((960, 540), getattr(Image, 'Resampling', Image).NEAREST)
        stages['resize'].append(time.perf_counter() - started)
        started = time.perf_counter()
        pixels = np.frombuffer(resized.tobytes('raw', 'BGR'), dtype=np.uint8).reshape((540, 960, 3))
        stages['raw_bgr'].append(time.perf_counter() - started)
        started = time.perf_counter()
        frame[106:646, 160:1120] = pixels
        stages['blit'].append(time.perf_counter() - started)
        started = time.perf_counter()
        rgb = np.asarray(picture)
        alternative = rgb[y[:, None], x[None, :], ::-1]
        stages['numpy_nearest'].append(time.perf_counter() - started)
        if not np.array_equal(pixels, alternative):
            raise RuntimeError('NumPy nearest candidate differs from Pillow reference')
        started = time.perf_counter()
        reference = renderer.render(view)
        stages['render'].append(time.perf_counter() - started)
        if not np.array_equal(frame, reference):
            raise RuntimeError('Manual stage profiling differs from reference pixels')
    print(json.dumps({name: {'median_ms': statistics.median(values) * 1000,
                            'mean_ms': statistics.mean(values) * 1000, 'max_ms': max(values) * 1000}
                      for name, values in stages.items()}, indent=2))


if __name__ == '__main__':
    main()
