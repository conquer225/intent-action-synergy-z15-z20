"""Generate deterministic numerical fixtures for the two RTL co-simulations."""
import argparse
from pathlib import Path
import sys
import numpy as np
from scipy import signal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/workspace/integrations'))
from pl_accel.eeg import BANDS, EEGModel, EEGReference
from pl_accel.mapping import MapScene, render_reference


def declaration(name, values):
    values = np.asarray(values).ravel().tolist()
    rows = [','.join(str(int(v)) for v in values[i:i+12]) for i in range(0, len(values), 12)]
    return 'static const int32_t '+name+'['+str(len(values))+']={\n'+',\n'.join(rows)+'\n};\n'


def fixtures():
    sos = np.array([signal.butter(2, band, btype='bandpass', fs=250, output='sos') for band in BANDS])
    csp = np.rint(np.random.default_rng(17).uniform(-.1, .1, (3, 2, 8))*2**14).astype(np.int32)
    model = EEGModel(np.rint(sos[:, :, [0, 1, 2, 4, 5]]*2**28).astype(np.int32),
        csp, [11, -7, 17, -9, 5, -3], -123456, window=32, hop=16)
    samples = np.random.default_rng(23).integers(-10000, 10001, (96, 8), dtype=np.int32)
    expected = EEGReference(model).feed(samples)
    eeg = '// Integer reference fixture; deterministic numeric data, separate from trained MI models.\n'
    eeg += declaration('eeg_fixture_params', model.parameter_words())
    eeg += declaration('eeg_fixture_samples', samples)
    eeg += declaration('eeg_fixture_expected', [[int(r['valid']), r['class_id'],
        r['score_q24'], *r['features'], r['sample_count']] for r in expected])
    rng = np.random.default_rng(71)
    scene = MapScene(rng.uniform([-3, -3, -.5], [3, 3, 6], (200, 3)),
        colors=rng.integers(0, 256, (200, 3), dtype=np.uint8),
        trajectory=[[-5, -1, 2], [0, 1, 2], [5, -1, 2]],
        width=63, height=47, focal=24, center=(31, 23), radius=1)
    rgb, stats = render_reference(scene)
    packed = (rgb[:, :, 0].astype(np.int32)<<16)|(rgb[:, :, 1].astype(np.int32)<<8)|rgb[:, :, 2]
    mapping = '// Independent raster reference: occlusion, clipping and trajectory.\n'
    mapping += declaration('map_fixture_params', scene.parameter_words())
    mapping += declaration('map_fixture_vertices', scene.vertex_words())
    mapping += declaration('map_fixture_frame', packed)
    mapping += declaration('map_fixture_stats', [stats[k] for k in ('visible_points', 'clipped_points', 'trajectory_segments')])
    return {'eeg_vectors.h': eeg, 'map_vectors.h': mapping}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'src/workspace/integrations/pl_accel/hls')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for name, content in fixtures().items():
        path = args.output/name
        if args.check:
            if path.read_text(encoding='ascii') != content:raise ValueError('fixture differs: '+name)
        else:
            args.output.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='ascii', newline='\n')
    print('PASS: independent EEG and raster numerical fixtures')


if __name__ == '__main__':main()
