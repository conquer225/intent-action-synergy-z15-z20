"""Real subprocess lifecycle tests using a non-audio fixture, never the MMIO player."""
from pathlib import Path
import sys
import tempfile
import time
import unittest

from audio_session import PcmSession


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.audio = PcmSession([sys.executable, str(Path(__file__).parent/'sim/pcm_player_process_stub.py')])
        self.addCleanup(self.audio.close)

    def asset(self, name, mode='hold'):
        path = self.root/name
        path.write_text(mode)
        return path

    def wait(self, predicate):
        end = time.monotonic()+5
        while time.monotonic() < end:
            view = self.audio.snapshot()
            if predicate(view):
                return view
            time.sleep(.01)
        self.fail('Timed out: '+str(self.audio.snapshot()))

    def test_play_stop_and_exact_resume(self):
        path = self.asset('video.wav')
        revision = self.audio.play(path, start_frame=48001)
        view = self.wait(lambda v: v['phase'] == 'feeding')
        self.assertEqual(view['revision'], revision)
        self.assertEqual(view['position_frames_estimate'], 48001)
        self.assertFalse(view['audible_verified'])
        old = self.audio.process
        started = time.monotonic()
        stopped = self.audio.stop()
        self.assertLess(time.monotonic()-started, .1)
        self.wait(lambda v: v['revision'] == stopped and v['phase'] == 'stopped')
        self.assertIsNotNone(old.poll())
        self.audio.play(path, start_frame=48002)
        view = self.wait(lambda v: v['phase'] == 'feeding')
        self.assertEqual(view['position_frames_estimate'], 48002)

    def test_switch_waits_for_previous_child(self):
        self.audio.play(self.asset('music.wav'))
        self.wait(lambda v: v['phase'] == 'feeding')
        old = self.audio.process
        next_path = self.asset('water.wav')
        self.audio.play(next_path)
        view = self.wait(lambda v: v.get('source') == str(next_path) and v['phase'] == 'feeding')
        self.assertIsNotNone(old.poll())
        self.assertNotEqual(view['pid'], old.pid)

    def test_completed_asset_is_not_restarted(self):
        self.audio.play(self.asset('help.wav', 'complete'))
        view = self.wait(lambda v: v['phase'] == 'completed' and v['pid'] is None)
        self.assertEqual(view['position_frames_estimate'], 480)
        time.sleep(.15)
        self.assertEqual(self.audio.snapshot()['pid'], None)
        self.assertEqual(self.audio.snapshot()['revision'], view['revision'])

    def test_failure_is_reported(self):
        self.audio.play(self.asset('bad.wav', 'failure'))
        view = self.wait(lambda v: v['phase'] == 'error' and v['pid'] is None)
        self.assertEqual(view['returncode'], 3)
        self.assertIn('fixture failure', view['errors'])

    def test_burst_keeps_only_latest_desired_state(self):
        self.audio.play(self.asset('music.wav', 'flood'))
        self.wait(lambda v: v['phase'] == 'feeding')
        old = self.audio.process
        for n in range(40):
            self.audio.play(self.asset('next.wav'), start_frame=n)
        stopped = self.audio.stop()
        self.wait(lambda v: v['revision'] == stopped and v['phase'] == 'stopped')
        self.assertIsNotNone(old.poll())

    def test_close_stops_before_caller_can_release_display(self):
        self.audio.play(self.asset('music.wav'))
        self.wait(lambda v: v['phase'] == 'feeding')
        old = self.audio.process
        self.audio.close()
        self.assertIsNotNone(old.poll())
        self.assertFalse(self.audio.worker.is_alive())
        with self.assertRaises(RuntimeError):
            self.audio.play(self.root/'music.wav')

    def test_invalid_request_does_not_replace_current_track(self):
        self.audio.play(self.asset('music.wav'))
        before = self.wait(lambda v: v['phase'] == 'feeding')
        for position in (-1, 28800000, True, 1.5):
            with self.assertRaises(ValueError):
                self.audio.play(self.root/'music.wav', start_frame=position)
        with self.assertRaises(FileNotFoundError):
            self.audio.play(self.root/'missing.wav')
        self.assertEqual(self.audio.snapshot()['revision'], before['revision'])


if __name__ == '__main__':
    unittest.main()
