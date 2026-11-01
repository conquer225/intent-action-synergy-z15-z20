"""Build the BGR label update's menu cache in ordinary RAM, never touch PL."""
import hashlib
import json
from pathlib import Path

import numpy as np

from system_hdmi import UnifiedDisplay


DISPLAY = Path('/home/xilinx/gl-hdmi-live-20261008-ea117349')
CANDIDATE_SHA = '623b063560b2bc65e795c614b48fbf846a8ae0290de6e8a6d01dbf99bdaa5996'
FILES = ('media_player.py', 'system_hdmi.py', 'frame_fitter.so',
         'menu-shells-portrait-live.npz')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    candidate = Path(__file__).resolve().parent
    if candidate.parent != Path('/home/xilinx') or not candidate.name.startswith('gl-video-path-20261009-'):
        raise ValueError('Only a private display payload directory is allowed')
    expected = json.loads((candidate / 'active-hashes.json').read_text())
    if any(digest(DISPLAY / name) != value for name, value in expected.items()):
        raise ValueError('Active display changed before preparation')
    if digest(candidate / 'system_hdmi.py') != CANDIDATE_SHA:
        raise ValueError('Candidate is not the pixel-tested BGR strip revision')
    for name in ('media_player.py', 'frame_fitter.so'):
        if digest(candidate / name) != expected[name]:
            raise ValueError('This label update must not replace other implementations')
    cache = candidate / FILES[-1]
    if cache.exists():
        raise ValueError('Do not overwrite a retained menu cache')
    media = json.loads((DISPLAY / 'media_state.json').read_text())
    display = UnifiedDisplay(media['eye_root'], live=True, dimensions=(288, 512))
    with np.load(DISPLAY / FILES[-1], allow_pickle=False) as old:
        metadata = json.loads(str(old['metadata'].item()))
        contract = dict(metadata['contract'], display_sha=CANDIDATE_SHA)
        if contract != display.shell_contract:
            raise ValueError('Fonts, layout or controller contract changed')
        if set(old.files) != set(display.shells) | {'metadata'}:
            raise ValueError('Menu page set changed')
        for page, pixels in display.shells.items():
            if not np.array_equal(pixels, old[page]):
                raise ValueError('Static menu pixels changed: ' + page)
    display.save_shell_cache(cache)
    restored = UnifiedDisplay(media['eye_root'], live=True, dimensions=(288, 512),
                              shell_cache=cache)
    if any(not np.array_equal(pixels, restored.shells[page])
           for page, pixels in display.shells.items()):
        raise ValueError('New menu cache did not round-trip exactly')
    if any(digest(DISPLAY / name) != value for name, value in expected.items()):
        raise ValueError('Active display changed during preparation')
    hashes = {name: digest(candidate / name) for name in FILES}
    with (candidate / 'candidate-hashes.json').open('x') as handle:
        json.dump(hashes, handle, indent=2)
    print(json.dumps(dict(pages=len(display.shells), exact_static_pixels=True,
        exact_cache_roundtrip=True, hardware_used=False, active_unchanged=True,
        hashes=hashes)))


if __name__ == '__main__':
    main()
