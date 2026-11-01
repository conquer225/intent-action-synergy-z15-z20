import json
from pathlib import Path
import tempfile
import unittest
from guardianloop_system.page_policy import PageLease,tasks_for,browser_input_path
from unittest.mock import patch


class PagePolicyTests(unittest.TestCase):
    def test_page_and_browser_clock_is_sampled_after_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'page.json';now=[10.]
            lease=PageLease(path,lambda:now[0],mode='live_readonly_hdmi')
            browser=browser_input_path(path)
            original=Path.read_text
            path.write_text(json.dumps(dict(page='home',mode='live_readonly_hdmi',
                physical_output_enabled=False,updated_monotonic=10.1)))
            browser.write_text(json.dumps(dict(mode='ssvep_browser_input',enabled=True,
                physical_output_enabled=False,token='0123456789abcdef',updated_monotonic=10.2)))
            def read_then_advance(value,*args,**kwargs):
                text=original(value,*args,**kwargs)
                now[0]=10.1 if value==path else 10.2
                return text
            with patch.object(Path,'read_text',read_then_advance):
                self.assertTrue(lease.enabled('ssvep_candidate'))
            self.assertTrue(lease.valid)
            self.assertTrue(lease.browser_requested)
            self.assertFalse(lease.enabled('seed_candidate'))

    def test_blocked_read_does_not_extend_page_or_browser_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'page.json';browser=browser_input_path(path)
            now=[10.];original=Path.read_text
            parent=dict(page='drive',mode='live_readonly_hdmi',
                        physical_output_enabled=False,updated_monotonic=10.)
            request=dict(mode='ssvep_browser_input',enabled=True,
                         physical_output_enabled=False,token='0123456789abcdef',
                         updated_monotonic=10.)
            path.write_text(json.dumps(parent));browser.write_text(json.dumps(request))
            def read_expired_page(value,*args,**kwargs):
                text=original(value,*args,**kwargs);now[0]=12.01
                return text
            lease=PageLease(path,lambda:now[0],mode='live_readonly_hdmi')
            with patch.object(Path,'read_text',read_expired_page):
                self.assertFalse(lease.enabled('ssvep_candidate'))
            self.assertFalse(lease.valid)
            now[0]=13.;parent.update(page='home',updated_monotonic=13.)
            path.write_text(json.dumps(parent))
            def read_expired_browser(value,*args,**kwargs):
                text=original(value,*args,**kwargs)
                if value==browser:now[0]=13.01
                return text
            lease=PageLease(path,lambda:now[0],mode='live_readonly_hdmi')
            with patch.object(Path,'read_text',read_expired_browser):
                self.assertFalse(lease.enabled('ssvep_candidate'))
            self.assertTrue(lease.valid)
            self.assertFalse(lease.browser_requested)

    def test_explicit_browser_input_only_enables_ssvep_with_valid_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'page.json';now=[10.]
            lease=PageLease(path,lambda:now[0],mode='live_readonly_hdmi')
            parent=dict(page='home',mode='live_readonly_hdmi',physical_output_enabled=False,
                        updated_monotonic=10.)
            request=dict(mode='ssvep_browser_input',enabled=True,physical_output_enabled=False,
                         token='0123456789abcdef',updated_monotonic=10.)
            path.write_text(json.dumps(parent))
            self.assertFalse(lease.enabled('ssvep_candidate'))
            browser_input_path(path).write_text(json.dumps(request));now[0]+=.3
            self.assertTrue(lease.enabled('ssvep_candidate'))
            self.assertFalse(lease.enabled('seed_candidate'))
            for change in ({'enabled':False},{'physical_output_enabled':True},
                           {'token':'bad'},{'updated_monotonic':float('nan')},
                           {'updated_monotonic':now[0]+10},{'updated_monotonic':now[0]-4}):
                browser_input_path(path).write_text(json.dumps(dict(request,**change)));now[0]+=.3
                parent['updated_monotonic']=now[0];path.write_text(json.dumps(parent))
                self.assertFalse(lease.enabled('ssvep_candidate'))
            request['updated_monotonic']=now[0]
            browser_input_path(path).write_text(json.dumps(request))
            path.write_text('broken');now[0]+=.3
            self.assertFalse(lease.enabled('ssvep_candidate'))
    def test_required_lanes_never_depend_on_page(self):
        for page in ('home','drive','video','music'):
            tasks=tasks_for(page)
            self.assertTrue(all(tasks[name] for name in ('filter_quality','emotion','fatigue','mi_virtual')))
            self.assertEqual(tasks['ssvep_candidate'],page=='drive')
            self.assertFalse(tasks['seed_candidate'])

    def test_missing_stale_future_foreign_leases_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'page.json';now=[10.]
            lease=PageLease(path,lambda:now[0])
            self.assertFalse(lease.enabled('ssvep_candidate'))
            data=dict(page='drive',mode='scripted_hdmi_replay',physical_output_enabled=False,updated_monotonic=10.)
            path.write_text(json.dumps(data));now[0]=10.3
            self.assertTrue(lease.enabled('ssvep_candidate'))
            now[0]=13.;self.assertFalse(lease.enabled('ssvep_candidate'))
            for changes in ({'updated_monotonic':14.},{'physical_output_enabled':True},{'mode':'live'}):
                path.write_text(json.dumps(dict(data,**changes)));now[0]+=.3
                self.assertFalse(lease.enabled('ssvep_candidate'))

    def test_suspension_and_resume_reset_lane_and_dont_reuse_baseline(self):
        import sys
        from unittest.mock import patch
        with patch.dict(sys.modules,{'page_policy':__import__('guardianloop_system.page_policy',fromlist=['PageLease'])}):
            from pynq_guardianloop.page_scheduled_replay import ScheduledLane
        class Lane:
            def __init__(self):self.reasons=[];self.packets=0
            def disconnect(self,reason):self.reasons.append(reason)
            def packet(self,*a,**kw):self.packets+=1;return ['result']
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'page.json';lane=Lane();scheduled=ScheduledLane(lane,path,'ssvep_candidate')
            now=[10.];scheduled.lease.clock=lambda:now[0]
            self.assertEqual(scheduled.packet(1),[])
            path.write_text(json.dumps(dict(page='drive',mode='scripted_hdmi_replay',physical_output_enabled=False,updated_monotonic=10.)))
            now[0]+=.3;self.assertEqual(scheduled.packet(2),['result'])
            self.assertEqual(lane.packets,1)
            self.assertEqual(lane.reasons,['page_task_suspended','page_task_resumed'])

    def test_paused_sink_does_not_enqueue_raw_packets(self):
        import sys
        from unittest.mock import patch
        with patch.dict(sys.modules,{'page_policy':__import__('guardianloop_system.page_policy',fromlist=['PageLease'])}):
            from pynq_guardianloop.page_scheduled_replay import ScheduledSink
        class Sink:
            def __init__(self):self.offered=[]
            def offer(self,*args):self.offered.append(args);return True
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'page.json';sink=Sink();scheduled=ScheduledSink(sink,path,'ssvep_candidate')
            now=[10.];scheduled.lease.clock=lambda:now[0]
            self.assertTrue(scheduled.offer(b'raw',0,10.));self.assertFalse(sink.offered)
            path.write_text(json.dumps(dict(page='drive',mode='scripted_hdmi_replay',physical_output_enabled=False,updated_monotonic=10.)))
            now[0]+=.3;self.assertTrue(scheduled.offer(b'raw',0,10.3))
            self.assertEqual(sink.offered,[(b'raw',0,10.3)])

    def test_live_menu_standalone_and_crashed_session_have_distinct_policies(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'page.json';now=[10.]
            lease=PageLease(path,lambda:now[0],mode='live_readonly_hdmi',
                            standalone_tasks=('ssvep_candidate','seed_candidate'))
            self.assertTrue(lease.enabled('ssvep_candidate'))
            self.assertTrue(lease.enabled('seed_candidate'))
            data=dict(page='video',mode='live_readonly_hdmi',physical_output_enabled=False,
                      updated_monotonic=10.3)
            path.write_text(json.dumps(data));now[0]=10.3
            self.assertFalse(lease.enabled('ssvep_candidate'))
            self.assertFalse(lease.enabled('seed_candidate'))
            for task in ('filter_quality','emotion','fatigue','mi_virtual'):
                self.assertTrue(lease.enabled(task))
            data['page']='drive';data['updated_monotonic']=10.6
            path.write_text(json.dumps(data));now[0]=10.6
            self.assertTrue(lease.enabled('ssvep_candidate'))
            now[0]=13.;self.assertFalse(lease.enabled('ssvep_candidate'))
            self.assertTrue(lease.enabled('emotion'))
            path.write_text('broken');now[0]+=0.3
            self.assertFalse(lease.enabled('ssvep_candidate'))
            path.unlink();now[0]+=0.3
            self.assertTrue(lease.enabled('ssvep_candidate'))
