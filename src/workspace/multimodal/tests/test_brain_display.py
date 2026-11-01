import unittest
from intent_one.brain_display import BrainDisplay,MiTrial
CHANNELS=['F3','F4','C3','C4','T7','T8','O1','O2']
class BrainDisplayTests(unittest.TestCase):
    def test_reference_predictions_do_not_send_commands_or_switch_page(self):
        display=BrainDisplay()
        status={'stale':False,'fatigue':{'valid':True,'level':'severe','offline':False,'emotion':{'valid':True,'label':'horror'}}}
        row=dict(source='live',state='active',input_state='ready',quality={'ready':True},channels=CHANNELS,
                 enabled=True,control_enabled=False,production_eligible=False,model_status='experimental_unpromoted',
                 result={'label':'left','source':'live','control_enabled':False,'window_start':0,'window_end_exclusive':1000},id='trial')
        result=display.observe(status,row)
        self.assertEqual(result['fatigue'],'severe');self.assertEqual(result['emotion'],'horror');self.assertEqual(result['mi_label'],'left')
        result=display.observe(dict(status,stale=True),dict(row,source='replay'))
        self.assertIsNone(result['mi_label']);self.assertIsNone(result['emotion'])
    def test_mi_trial_sends_observation_only_and_waits_for_actual_presentation(self):
        calls=[]
        def send(packet):
            calls.append(packet)
            return dict(id='new',state='awaiting_presentation' if packet['action']=='start' else 'active')
        trial=MiTrial(send)
        trial.start('left',1)
        self.assertEqual(calls,[{'action':'start','target':'left','virtual_control':False}])
        trial.presented(1.1);self.assertEqual(calls[-1]['action'],'presented')
        self.assertEqual(calls[-1]['browser_onset_ms'],1100)
        trial.tick(1.2);self.assertEqual(len(calls),2)
        trial.tick(1.6);self.assertEqual(calls[-1]['action'],'heartbeat')
        trial.stop();self.assertEqual(calls[-1]['action'],'stop')
if __name__=='__main__':unittest.main()
