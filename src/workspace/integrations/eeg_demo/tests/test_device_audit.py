import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'runtime/system_runtime'),str(ROOT.parent/'guardianloop_team_20261017_03/projects/codex_project/brain_eye_coexist/candidate/eye/src')]
from guardianloop_system.eye_devices import EyeDeviceController


class BusyLink:
    def __init__(self):self.enabled='hand';self.pending=True
    def snapshot(self):return {'enabled':self.enabled,'connected':True,'pending':self.pending}
    def stop(self,reason='stop'):self.enabled=None
    def request(self,*_):return False


class AuditTests(unittest.TestCase):
    def test_busy_link_rejection_is_not_reported_as_submitted_action(self):
        link=BusyLink();c=EyeDeviceController(link,0);c._enter('hand',0)
        link.enabled='hand';c.device_update(0);c.presented(c.page_id,0)
        self.assertFalse(c.choose(2,2))
        self.assertIn('未提交',c.snapshot(2)['last_action'])
        self.assertIsNone(c.snapshot(2)['last_selection'])


if __name__=='__main__':unittest.main()
