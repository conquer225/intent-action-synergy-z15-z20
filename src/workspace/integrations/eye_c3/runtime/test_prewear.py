import unittest
from prewear import hdmi_preflight
from guardianloop_system.core import SystemController


class PrewearTests(unittest.TestCase):
    def test_specific_failures_and_ready(self):
        s=dict(page='drive',reading=False,direction_armed=True,alerts={})
        b=dict(policy='ssvep-hdmi-experimental-v1',input=dict(ready=True),raw_recording_supported=True)
        self.assertTrue(hdmi_preflight(s,b)['ready'])
        for fields,reason in (({'page':'home'},'速度'),({'direction_armed':False},'启用'),
                              ({'reading':True},'呈现'),({'alerts':{'fatigue':'locked'}},'疲劳'),
                              ({'hdmi_stimulus':{'preparing':True}},'录制')):
            gate=hdmi_preflight(dict(s,**fields),b)
            self.assertFalse(gate['ready']);self.assertIn(reason,gate['reason'])
        self.assertFalse(hdmi_preflight(s,{})['ready'])

    def test_setup_not_timed_but_actual_trial_times_out(self):
        c=SystemController(100);c.direction_requires_start=True
        c._enter('drive',100);c.presented(c.page_id,100)
        c.tick(120);self.assertEqual(c.page,'drive')
        self.assertIsNone(c.direction_idle_deadline)
        self.assertFalse(c.direction_started(c.page_id,120))
        self.assertTrue(c.arm_virtual_direction(120))
        self.assertTrue(c.direction_started(c.page_id,120))
        c.tick(134.9);self.assertEqual(c.page,'drive')
        c.tick(135);self.assertEqual(c.page,'home')
        self.assertEqual(c.direction,'stop')
