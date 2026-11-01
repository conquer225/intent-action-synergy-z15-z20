import subprocess
import sys
import unittest


class SilentAudioTests(unittest.TestCase):
    def test_board_feature_path_imports_without_scipy_or_new_numpy_framing(self):
        result = subprocess.run([sys.executable, '-c', '''
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'scipy' or name.startswith('scipy.'):
        raise ImportError('board has no scipy')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
import numpy as np
if hasattr(np.lib.stride_tricks, 'sliding_window_view'):
    del np.lib.stride_tricks.sliding_window_view
from z20_compute.audio import sound_features, spectrum
t=np.arange(16000)/16000.
features=sound_features(.2*np.sin(2*np.pi*1000*t))
assert features.shape == (40,) and np.isfinite(features).all()
frequencies, amplitudes=spectrum(.2*np.sin(2*np.pi*1000*t))
assert frequencies[np.argmax(amplitudes)] == 1000
try: sound_features(np.zeros(16000))
except ValueError as exc: assert str(exc) == 'silence'
else: raise AssertionError('silence accepted')
'''], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class KeyTests(unittest.TestCase):
    def test_startup_held_waits_release_bounce_and_hold_do_not_repeat(self):
        from z20_compute.headless_keys import KeyGestures
        keys = KeyGestures()
        for now in (0., .1, 1., 2.):
            self.assertEqual(keys.update(True, True, now), [])
        keys.update(False, False, 2.01)
        self.assertEqual(keys.update(False, False, 2.07), [])
        keys.update(True, False, 3.)
        keys.update(False, False, 3.02)
        self.assertEqual(keys.update(False, False, 3.08), [])
        keys.update(True, False, 4.)
        keys.update(True, False, 4.06)
        self.assertEqual(keys.update(True, False, 4.87), ['key1_long'])
        self.assertEqual(keys.update(True, False, 6.), [])
        keys.update(False, False, 6.01)
        self.assertEqual(keys.update(False, False, 6.07), [])

    def test_short_presses_and_view_cycle(self):
        from z20_compute.headless_keys import KeyGestures, Navigation
        keys, nav = KeyGestures(), Navigation()
        keys.update(False, False, 0.); keys.update(False, False, .06)
        keys.update(True, False, .2); keys.update(True, False, .26)
        keys.update(False, False, .4)
        events = keys.update(False, False, .46)
        self.assertEqual(events, ['key1_short'])
        nav.apply(events[0]); self.assertEqual(nav.page, 'emotion')
        nav.apply('key2_short'); self.assertEqual(nav.detail, 1)
        nav.apply('key1_long'); self.assertEqual(nav.page, 'overview')
        pages = []
        for _ in range(9):
            nav.apply('key1_short'); pages.append(nav.page)
        self.assertEqual(pages, ['emotion', 'fatigue', 'depth', 'cloud', 'person_dog',
                                 'sound', 'audio', 'adda', 'overview'])


if __name__ == '__main__': unittest.main()
