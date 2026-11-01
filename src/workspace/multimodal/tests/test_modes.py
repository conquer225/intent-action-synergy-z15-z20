import unittest
from intent_one.app import Session
from intent_one.simulation import SimulatedPeer
class ModesTests(unittest.TestCase):
    def test_top_mode_cycles_and_never_inherits_enabled_task(self):
        session=Session(SimulatedPeer,simulation=True)
        self.assertEqual(session.menu.snapshot(0)['interaction_mode'],'eye')
        session.command('1',0);session.command('e',1);peer=session.menu.tasks.peer
        session.command('mode_next',2)
        self.assertEqual(peer.commands[-1][:2],('all','estop'))
        self.assertEqual(session.menu.snapshot(2)['interaction_mode'],'emg')
        self.assertFalse(session.menu.tasks.enabled)
        session.command('mode_next',3)
        self.assertEqual(session.menu.snapshot(3)['interaction_mode'],'eeg')
        session.command('mode_next',4)
        self.assertEqual(session.menu.snapshot(4)['labels'],['灵巧手','倒立摆','表达与媒体'])
        session.close()
if __name__=='__main__':unittest.main()
