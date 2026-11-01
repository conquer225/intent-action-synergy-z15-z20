"""Live distance telemetry and explicit positioning, without board interaction."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from guide import DIRECTION_POINTS, Guide, View
from guide_render import Renderer
from media_menu import MenuView
from tracking import Tracking


class DistanceDisplayTests(unittest.TestCase):
    @staticmethod
    def event(distance=417.0):
        return dict(samples=30, left=28, right=20, pupil_left=26,
                    pupil_right=18, distance_mm=distance)

    def test_fresh_measurement_keeps_tenth_of_a_centimetre(self):
        telemetry = Tracking()
        self.assertTrue(telemetry.update(self.event(), 10))
        self.assertIn("约 41.7 cm", telemetry.lines(10)[0])
        self.assertIn("约 41.7 cm", telemetry.lines(11.5)[0])
        self.assertTrue(telemetry.update(self.event(426.0), 11.5))
        self.assertIn("约 42.6 cm", telemetry.lines(11.5)[0])
        self.assertNotIn("41.7", telemetry.lines(11.5)[0])

    def test_expired_distance_is_unknown_and_cannot_look_current(self):
        telemetry = Tracking(reference_cm=(40, 43))
        telemetry.update(self.event(), 10)
        lines = telemetry.lines(11.501)
        self.assertIn("距离 未知", lines[0])
        self.assertIn("等待新数据", lines[0])
        self.assertNotIn("41.7", " ".join(lines))
        self.assertIn("上次可用参考", lines[1])

    def test_missing_distance_does_not_reuse_last_value_or_show_zero(self):
        telemetry = Tracking()
        self.assertIn("距离 未知", telemetry.lines(1)[0])
        telemetry.update(self.event(), 10)
        self.assertTrue(telemetry.update(self.event(None), 10.5))
        line = telemetry.lines(10.5)[0]
        self.assertIn("距离 未知", line)
        self.assertNotIn("41.7", line)
        self.assertNotIn("0.0 cm", line)

    def test_reference_is_explicit_and_separate_from_live_distance(self):
        telemetry = Tracking(reference_cm=(40, 43))
        telemetry.update(self.event(606.0), 10)
        lines = telemetry.lines(10)
        self.assertIn("约 60.6 cm", lines[0])
        self.assertIn("上次可用参考", lines[1])
        self.assertIn("40", lines[1])
        self.assertIn("43", lines[1])
        ordinary = Tracking()
        ordinary.update(self.event(606.0), 10)
        self.assertNotIn("上次可用参考", " ".join(ordinary.lines(10)))

    def test_positioning_waits_for_explicit_start_and_can_be_cancelled(self):
        state = Guide(relaxed=True, points=DIRECTION_POINTS, collect_seconds=6)
        state.phase = "positioning"
        state.point, state.ack = 2, True
        state.response(2, True)
        self.assertEqual(state.tick(100_000).phase, "positioning")
        state.start(100_001)
        self.assertEqual(state.phase, "prepare")
        self.assertEqual(state.point, 0)
        self.assertIsNone(state.ack)
        self.assertEqual(state.tick(100_005.9).phase, "prepare")
        self.assertEqual(state.tick(100_006).phase, "settle")
        state.phase = "positioning"
        state.cancel()
        self.assertEqual(state.tick(200_000).phase, "cancelled")

    def assert_cached_distance_updates(self, view, cache_attribute):
        renderer = Renderer(local_media=True, relative=True)
        baseline = renderer.render(view)
        original_cache = getattr(renderer, cache_attribute)
        original_stored = original_cache.copy()
        telemetry = Tracking(reference_cm=(40, 43))
        telemetry.update(self.event(417.0), 10)
        first = renderer.render(replace(view, tracking=telemetry.lines(10)))
        # Enabling telemetry may reserve layout space once. Numeric updates
        # after that must reuse the static page without embedding old text.
        cache = getattr(renderer, cache_attribute)
        stored = cache.copy()
        np.testing.assert_array_equal(original_cache, original_stored)
        telemetry.update(self.event(426.0), 10.5)
        latest_view = replace(view, tracking=telemetry.lines(10.5))
        latest = renderer.render(latest_view)
        self.assertFalse(np.array_equal(first, latest))
        self.assertIs(getattr(renderer, cache_attribute), cache)
        np.testing.assert_array_equal(cache, stored)
        independent = Renderer(local_media=True, relative=True).render(latest_view)
        np.testing.assert_array_equal(latest, independent)
        stale_view = replace(view, tracking=telemetry.lines(12.001))
        stale = renderer.render(stale_view)
        self.assertFalse(np.array_equal(latest, stale))
        np.testing.assert_array_equal(
            stale, Renderer(local_media=True, relative=True).render(stale_view))
        np.testing.assert_array_equal(renderer.render(view), baseline)
        np.testing.assert_array_equal(cache, stored)

    def test_menu_distance_refresh_preserves_cached_menu(self):
        self.assert_cached_distance_updates(
            MenuView(phase="menu", title="主页", labels=("句子发声", "看视频", "听音乐"),
                     detail="等待有效注视", footer="PS_KEY0 重新标定", page_id=1),
            "media_base")

    def test_selection_distance_refresh_preserves_cached_selection(self):
        self.assert_cached_distance_updates(
            View(phase="selection", detail="等待有效注视", hover=1, progress=.5),
            "selection_base")

    def test_video_distance_refresh_preserves_cached_shell_and_picture(self):
        self.assert_cached_distance_updates(
            MenuView(phase="video", title="正在观看", footer="PS_KEY1 退出",
                     page_id=2, video_frame=3,
                     video_image=Image.new("RGB", (640, 360), (7, 31, 95))),
            "video_shell")


if __name__ == "__main__":
    unittest.main()
