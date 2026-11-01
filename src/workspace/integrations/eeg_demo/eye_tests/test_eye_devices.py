import sys
from pathlib import Path
import unittest
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime/system_runtime'))
BASELINE=Path(os.environ.get('GL_BASELINE_ROOT',str(ROOT.parent/'guardianloop_team_20261017_03')))
sys.path.insert(0, str(BASELINE/'projects/codex_project/brain_eye_coexist/candidate/eye/src'))

from guardianloop_system.eye_devices import EyeDeviceController


class Link:
    def __init__(self):
        self.calls = []
        self.view = dict(connected=False, enabled=None, pending=False, message='等待启用')

    def request(self, device, action):
        self.calls.append((device, action))
        self.view['pending'] = True
        return True

    def stop(self, reason='stop'):
        self.calls.append(('all', 'estop'))
        self.view.update(enabled=None, pending=False, connected=False, message='等待注视启用')

    def snapshot(self):
        return dict(self.view)


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.link = Link()
        self.now = 10.
        self.controller = EyeDeviceController(self.link, self.now)
        self.ready()

    def ready(self):
        self.controller.presented(self.controller.page_id, self.now)
        self.now += 1.3

    def choose(self, region):
        self.assertTrue(self.controller.choose(region, self.now))
        self.ready()

    def test_gaze_opens_hand_with_fixed_actions_and_ack_required_before_pose(self):
        for index in range(40):
            self.now += .05
            self.controller.gaze(dict(valid=True, x=.1, monotonic_ns=int(self.now*1e9)), self.now)
        self.assertEqual(self.controller.page, 'equipment')
        self.ready()
        self.choose(0)
        self.assertEqual(self.controller.page, 'hand')
        self.assertEqual(self.controller.labels(), ('张开', '停止操作', '闭合'))
        self.choose(0)
        self.assertEqual(self.link.calls[-1], ('hand', 'enable'))
        self.link.view.update(connected=True, enabled='hand', pending=False)
        self.controller.device_update(self.now)
        self.ready()
        self.assertTrue(self.controller.snapshot(self.now)['physical_output_enabled'])
        self.assertEqual(self.controller.labels(), ('张开', '停止操作', '闭合'))
        self.choose(2)
        self.assertEqual(self.link.calls[-1], ('hand', 'close'))
        self.choose(1)
        self.assertEqual(self.controller.page, 'hand')
        self.assertIsNone(self.link.view['enabled'])
        self.choose(1)
        self.assertEqual(self.controller.page, 'equipment')
        self.assertIsNone(self.link.view['enabled'])

    def test_pendulum_balance_and_turns_require_separate_enables(self):
        self.choose(0); self.choose(1)
        self.assertEqual(self.controller.page, 'pendulum_menu')
        self.choose(0); self.choose(0)
        self.assertEqual(self.link.calls[-1], ('pendulum', 'enable'))
        self.link.view.update(connected=True, enabled='pendulum', pending=False)
        self.controller.device_update(self.now); self.ready(); self.choose(0)
        self.assertEqual(self.link.calls[-1], ('pendulum', 'start'))
        self.choose(2)
        self.assertEqual(self.link.calls[-1], ('pendulum', 'stop'))
        self.choose(1); self.choose(1); self.choose(2)
        self.assertIsNone(self.link.view['enabled'])
        self.choose(0)
        self.link.view.update(connected=True, enabled='pendulum', pending=False)
        self.controller.device_update(self.now); self.ready(); self.choose(2)
        self.assertEqual(self.link.calls[-1], ('pendulum', 'right'))

    def test_reading_guard_and_signal_loss_revoke_enabled_device(self):
        self.choose(0); self.choose(0)
        self.link.view.update(connected=True, enabled='hand', pending=False)
        self.controller.device_update(self.now)
        self.assertFalse(self.controller.choose(2, self.now))
        self.ready()
        self.controller.signal_lost(self.now)
        self.assertIsNone(self.link.view['enabled'])
        self.assertFalse(self.controller.snapshot(self.now)['devices']['enabled'])

    def test_existing_media_and_speed_routes_remain_available(self):
        self.choose(2); self.choose(0)
        self.assertEqual(self.controller.page, 'video')
        self.controller.force_stop(self.now); self.ready()
        self.choose(0); self.choose(2)
        self.assertEqual(self.controller.page, 'speed')


if __name__ == '__main__':
    unittest.main()
