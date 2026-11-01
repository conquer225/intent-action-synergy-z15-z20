import unittest
from intent_one.menu import Menu
from intent_one.tasks import TaskController
from test_runtime import Transport

class MenuTests(unittest.TestCase):
    def test_pendulum_turn_submenu_routes_left_right_and_back(self):
        c=TaskController(Transport);m=Menu(c);m.select('eye','pendulum',0);c.enable()
        m.choose(1,2);self.assertFalse(c.enabled)
        m.choose(0,3);self.assertEqual(m.labels(),['左动作','右动作','返回'])
        m.choose(0,4);self.assertEqual(c.peer.commands[-1][:2],('pendulum','left'))
        m.choose(1,6);self.assertEqual(c.peer.commands[-1][:2],('pendulum','right'))
        m.choose(2,8);self.assertEqual(m.page,'actions')
    def test_eyes_directly_select_action_without_other_confirmation(self):
        c=TaskController(Transport);m=Menu(c);m.select('eye','hand',0);c.enable();m.presented(0)
        for n in range(2,36):
            now=n*.1;m.gaze({'x':.5,'valid':True,'monotonic_ns':int(now*1e9)},now)
        self.assertTrue(any(a=='close' for _,a,_ in c.peer.commands))
        count=len(c.peer.commands)
        for n in range(36,50):m.gaze({'x':.5,'valid':True,'monotonic_ns':int(n*.1*1e9)},n*.1)
        self.assertEqual(len(c.peer.commands),count)
    def test_process_page_cannot_trigger_motion_and_switch_stops(self):
        c=TaskController(Transport);m=Menu(c);m.select('eye','hand',0);c.enable()
        m.page_to('process',1)
        self.assertFalse(c.enabled)
        self.assertEqual(c.peer.commands[-1][:2],('all','estop'))
        c.enable();commands=len(c.peer.commands);m.choose(0,3)
        self.assertEqual(len(c.peer.commands),commands)

if __name__=='__main__':unittest.main()
