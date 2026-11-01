"""User-facing device choices must not turn a stop into navigation."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'runtime/system_runtime'),
    str(ROOT.parent / 'guardianloop_team_20261017_03/projects/codex_project/brain_eye_coexist/candidate/eye/src')]
from guardianloop_system.eye_devices import EyeDeviceController
from test_eye_devices import Link


class DeviceNavigationTests(unittest.TestCase):
    def ready(self, controller, now):
        controller.presented(controller.page_id, now)
        return now + 1.3

    def test_first_centre_stop_keeps_page_and_second_confirmation_returns(self):
        for page, target, parent in (('hand', 'hand', 'equipment'),
                                      ('pendulum_balance', 'pendulum', 'pendulum_menu'),
                                      ('pendulum_turn', 'pendulum', 'pendulum_menu')):
            with self.subTest(page=page):
                link = Link()
                controller = EyeDeviceController(link, 10.)
                controller._enter(page, 10.)
                link.view.update(connected=True, enabled=target, pending=False)
                controller.device_update(10.)
                now = self.ready(controller, 10.)
                self.assertTrue(controller.choose(1, now))
                self.assertEqual(controller.page, page, 'stopping must not navigate')
                self.assertIsNone(link.snapshot()['enabled'])
                self.assertIn('返回', controller.labels()[1])
                self.assertFalse(controller.choose(1, now + .1))
                now = self.ready(controller, now + .2)
                self.assertTrue(controller.choose(1, now))
                self.assertEqual(controller.page, parent)

    def test_entry_prepares_once_after_presentation_and_fresh_eye_without_motion(self):
        for choice, page, target in ((0, 'hand', 'hand'), (1, 'pendulum_balance', 'pendulum')):
            with self.subTest(page=page):
                link = Link()
                controller = EyeDeviceController(link, 10.)
                now = self.ready(controller, 10.)
                controller.choose(0, now)
                now = self.ready(controller, now)
                controller.choose(choice, now)
                if choice == 1:
                    now = self.ready(controller, now)
                    controller.choose(0, now)
                self.assertEqual(controller.page, page)
                self.assertNotIn('启用', ''.join(controller.labels()))
                controller.service_device_entry(now, True)
                self.assertFalse(any(action == 'enable' for _, action in link.calls))
                now = self.ready(controller, now)
                controller.service_device_entry(now, True)
                self.assertEqual(link.calls[-1], (target, 'enable'))
                controller.service_device_entry(now + .05, True)
                self.assertEqual(sum(action == 'enable' for _, action in link.calls), 1)
                self.assertFalse(any(action in ('open','close','start','left','right') for _, action in link.calls))

    def test_disconnect_keeps_labels_and_requires_new_selection_before_preparing(self):
        link = Link()
        controller = EyeDeviceController(link, 10.)
        controller._enter('pendulum_balance', 10.)
        link.view.update(connected=True, enabled='pendulum', pending=False)
        controller.device_update(10.)
        now = self.ready(controller, 10.)
        labels = controller.labels()
        link.view.update(connected=False, enabled=None, pending=False)
        controller.device_update(now)
        now = self.ready(controller, now)
        controller.service_device_entry(now, True)
        self.assertEqual(controller.page, 'pendulum_balance')
        self.assertEqual(controller.labels(), labels)
        self.assertFalse(any(action == 'enable' for _, action in link.calls))
        self.assertTrue(controller.choose(0, now))
        self.assertEqual(link.calls[-1], ('pendulum', 'enable'))
        self.assertFalse(any(action == 'start' for _, action in link.calls))

    def test_held_centre_does_not_chain_stop_into_return(self):
        link = Link()
        controller = EyeDeviceController(link, 10.)
        controller._enter('pendulum_balance', 10.)
        now = self.ready(controller, 10.)
        for _ in range(110):
            now += .05
            controller.gaze(dict(valid=True, x=.5, monotonic_ns=int(now * 1e9)), now)
            controller.presented(controller.page_id, now)
        self.assertEqual(controller.page, 'pendulum_balance')
        self.assertTrue(controller.return_pending)
        self.assertEqual(controller.selection.confirmations, 1)

    def test_optional_mood_prompt_never_takes_over_device_but_fatigue_still_stops(self):
        link = Link()
        controller = EyeDeviceController(link, 10.)
        controller._enter('pendulum_balance', 10.)
        controller.monitor('emotion', 'horror', 11., source='GAMEEMO_condition', qualified=True)
        self.assertEqual(controller.page, 'pendulum_balance')
        self.assertEqual(controller.monitor_labels['emotion']['label'], 'horror')
        controller.monitor('fatigue', 'severe_candidate', 12., source='live_model_candidate', qualified=True)
        self.assertEqual(controller.page, 'fatigue_alert')
        self.assertIsNone(link.snapshot()['enabled'])

    def test_invalid_eye_cancels_entry_intent_and_cannot_enable_on_recovery(self):
        link = Link()
        controller = EyeDeviceController(link, 10.)
        now = self.ready(controller, 10.)
        controller.choose(0, now)
        now = self.ready(controller, now)
        controller.choose(0, now)
        now = self.ready(controller, now)
        controller.service_device_entry(now, False)
        controller.service_device_entry(now + .1, True)
        self.assertFalse(any(action == 'enable' for _, action in link.calls))


if __name__ == '__main__':
    unittest.main()
