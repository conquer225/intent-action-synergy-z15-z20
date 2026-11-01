"""Real framed TCP proves menu preparation never replays an action."""
import time
import unittest
from types import SimpleNamespace

from test_device_link import Peer
import test_device_link
from test_eye_devices import EyeDeviceController
from guardianloop_system.device_link import DeviceLink, service_eye


class DeviceEntryTCPTests(unittest.TestCase):
    def enter(self,link):
        now=time.monotonic();controller=EyeDeviceController(link,now)
        for region in (0,1,0):
            controller.presented(controller.page_id,now);now+=1.3
            self.assertTrue(controller.choose(region,now))
        controller.presented(controller.page_id,now);now+=1.3
        return controller,SimpleNamespace(control_enabled=True,last_valid=now),now

    def wait(self,link,condition):
        # Existing host peer helper services the actual lease while waiting.
        test_device_link.LinkTests.wait(self,link,condition)

    def test_menu_entry_prepares_once_then_requires_fresh_action_after_ack(self):
        peer=Peer();link=DeviceLink('127.0.0.1',peer.port)
        try:
            controller,eye,now=self.enter(link)
            service_eye(link,controller,eye,now)
            self.wait(link,lambda:link.snapshot()['enabled']=='pendulum')
            self.assertEqual(sum(r['action']=='enable' for r in peer.rows),1)
            self.assertFalse(any(r['action']=='start' for r in peer.rows))
            service_eye(link,controller,eye,now)
            now+=.1
            self.assertFalse(controller.choose(0,now))
            controller.presented(controller.page_id,now);now+=1.3
            self.assertTrue(controller.choose(0,now))
            self.wait(link,lambda:not link.snapshot()['pending'])
            self.assertEqual(sum(r['action']=='start' for r in peer.rows),1)
            controller.presented(controller.page_id,now);now+=1.3
            controller.choose(1,now)
            self.assertTrue(peer.closed.wait(.4))
            self.assertEqual(controller.page,'pendulum_balance')
            self.assertIsNone(link.snapshot()['enabled'])
        finally:link.close();peer.close()

    def test_rejected_entry_stays_on_page_and_never_retries_on_its_own(self):
        peer=Peer(reject_enable=True);link=DeviceLink('127.0.0.1',peer.port)
        try:
            controller,eye,now=self.enter(link)
            service_eye(link,controller,eye,now)
            self.wait(link,lambda:not link.snapshot()['pending'])
            for _ in range(5):service_eye(link,controller,eye,now)
            self.assertEqual(controller.page,'pendulum_balance')
            self.assertIsNone(link.snapshot()['enabled'])
            self.assertIn('neutral_pending_retry',controller.device_presentation()['message'])
            self.assertEqual(sum(r['action']=='enable' for r in peer.rows),1)
            self.assertFalse(any(r['action']=='start' for r in peer.rows))
        finally:link.close();peer.close()

    def test_centre_cancels_pending_preparation_without_late_motion(self):
        peer=Peer(hold_enable=True);link=DeviceLink('127.0.0.1',peer.port)
        try:
            controller,eye,now=self.enter(link)
            service_eye(link,controller,eye,now)
            self.wait(link,lambda:any(r['action']=='enable' for r in peer.rows))
            self.assertTrue(controller.choose(1,now))
            self.assertTrue(peer.closed.wait(.4))
            service_eye(link,controller,eye,now)
            self.assertEqual(controller.page,'pendulum_balance')
            self.assertIsNone(link.snapshot()['enabled'])
            self.assertFalse(any(r['action']=='start' for r in peer.rows))
        finally:link.close();peer.close()
