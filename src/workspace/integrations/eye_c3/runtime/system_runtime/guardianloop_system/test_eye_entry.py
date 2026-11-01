import unittest
from guardianloop_system.core import SystemController
from guardianloop_system.eye_entry import EyeEntryCheck


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.entry=EyeEntryCheck(SystemController.read_seconds)

    def event(self,now,x=.5,valid=True):
        return dict(valid=valid,x=x,monotonic_ns=int(now*1e9))

    def test_no_checks_before_actual_presentation_and_read_gate(self):
        for i in range(40):self.entry.update(self.event(10+i*.05),10+i*.05)
        self.assertEqual(self.entry.rows,[])
        self.entry.presented(self.entry.view(12),12)
        for i in range(20):self.entry.update(self.event(12+i*.05),12+i*.05)
        self.assertEqual(self.entry.selection.progress,0)
        self.assertEqual(self.entry.rows,[])

    def test_stale_invalid_and_duplicate_packets_do_not_pass(self):
        self.entry.presented(self.entry.view(10),10)
        for i in range(40):
            now=11.3+i*.05
            self.entry.update(self.event(now-1),now)
            self.entry.update(self.event(now,valid=False),now)
        self.assertEqual(self.entry.rows,[])
        now=14.
        event=self.event(now)
        for i in range(40):self.entry.update(event,now+i*.005)
        self.assertEqual(self.entry.rows,[])
        self.assertFalse(self.entry.snapshot()['accuracy_estimate'])

    def test_terminal_views_are_valid(self):
        self.entry.rows=[dict(correct=True)]*3
        self.assertIn('通过',self.entry.view(10).detail)
        self.entry.failed=True
        self.assertIn('未通过',self.entry.view(10).detail)


if __name__=='__main__':unittest.main()
