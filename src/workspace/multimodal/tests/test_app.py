import unittest
from intent_one.app import Session
from intent_one.simulation import SimulatedPeer
class AppTests(unittest.TestCase):
    def test_simulated_menu_clicks_are_disabled_for_live_sessions(self):
        s=Session(SimulatedPeer,simulation=True);s.menu.presented(0);s.command('choose 2',2)
        self.assertEqual(s.menu.page,'more');s.close()
        live=Session(SimulatedPeer,simulation=False);live.menu.presented(0)
        with self.assertRaises(RuntimeError):live.command('choose 2',2)
        self.assertEqual(live.menu.page,'home');live.close()
    def test_process_display_cannot_enable_an_actuator(self):
        s=Session(SimulatedPeer,simulation=True);s.command('1',0);s.command('process',1)
        with self.assertRaises(RuntimeError):s.command('e',2)
        self.assertFalse(s.menu.tasks.enabled);s.close()
    def test_simulation_is_explicit_and_mode_switch_disables(self):
        s=Session(SimulatedPeer,simulation=True)
        s.command('1',0);s.command('e',1);s.command('close',2)
        self.assertTrue(s.menu.tasks.enabled)
        self.assertEqual(s.menu.snapshot(2)['origin'],'simulation')
        s.command('4',3);self.assertFalse(s.menu.tasks.enabled)
        s.command('process',4);self.assertEqual(s.menu.snapshot(4)['page'],'process')
        s.close()
    def test_live_eye_without_calibration_cannot_enable(self):
        s=Session(SimulatedPeer,simulation=False);s.command('1',0)
        with self.assertRaises(RuntimeError):s.command('e',1)
        self.assertFalse(s.menu.tasks.enabled);s.close()
if __name__=='__main__':unittest.main()
