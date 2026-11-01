import unittest

from z20_compute.visual_demo import DemoState


class DemoStateTests(unittest.TestCase):
    def test_mode_fencing_duplicates_and_expiration(self):
        clock=[10.0]
        state=DemoState(now=lambda:clock[0])
        session=state.attach_renderer()
        state.command('eye',1,'enter')
        epoch=state.snapshot()['epoch']
        self.assertTrue(state.accept_frame(session,epoch,1,b'new frame'))
        self.assertFalse(state.accept_frame(session,epoch,1,b'duplicate'))
        state.command('eye',2,'right')
        self.assertEqual(state.snapshot()['action']['name'],'inject_right')
        self.assertFalse(state.command('eye',2,'right')['accepted'])
        state.command('eye',3,'back')
        self.assertIsNone(state.latest())
        self.assertFalse(state.accept_frame(session,epoch,2,b'old mode'))
        current=state.snapshot()['epoch']
        self.assertTrue(state.accept_frame(session,current,3,b'latest'))
        clock[0]=12.01
        self.assertIsNone(state.latest())
        self.assertFalse(state.snapshot()['renderer_online'])

    def test_four_mode_navigation_cannot_emit_device_commands(self):
        state=DemoState()
        self.assertEqual(state.command('eye',1,'right')['mode'],'spectrum')
        self.assertEqual(state.command('eye',2,'right')['mode'],'npu')
        state.command('eye',3,'enter')
        self.assertEqual(state.command('eye',4,'left')['sample_index'],2)
        self.assertFalse(state.snapshot()['actuator_control'])
        with self.assertRaises(ValueError):state.command('eye',5,'hand_open')

    def test_renderer_reconnect_rejects_previous_session(self):
        state=DemoState()
        old=state.attach_renderer();epoch=state.snapshot()['epoch']
        new=state.attach_renderer()
        self.assertNotEqual(old,new)
        self.assertFalse(state.accept_frame(old,epoch,1,b'old'))
        self.assertTrue(state.accept_frame(new,state.snapshot()['epoch'],1,b'new'))

    def test_lost_renderer_clears_results_even_when_local_producer_is_alive(self):
        clock=[10.];state=DemoState(now=lambda:clock[0]);state.attach_renderer()
        state.publish('npu',dict(valid=True,scores=[1,2,3]),epoch=state.epoch)
        self.assertTrue(state.snapshot()['data'])
        clock[0]+=2.01
        state.publish('npu',dict(valid=True,scores=[1,2,3]),epoch=state.epoch)
        self.assertEqual(state.snapshot()['data'],{})
