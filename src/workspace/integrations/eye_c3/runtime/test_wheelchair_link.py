import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bench_network_bridge import NetworkBridge
from dry_run_bridge import demo_snapshot
from test_network_bridge import FakeReceiver
from wheelchair_link import POLICY, UnifiedLink, ManualControl, PriorityStop, pending_stop, read_status, receiver_address


def player(now=10.):
    return dict(session_id='play-12345678', updated_monotonic=now, system=dict(
        mode='live_readonly_hdmi', page='drive', page_id=4, reading=False,
        force_stopped=False, direction_armed=True, alerts={}, eye_only=False,
        stimulus_enabled=True, hdmi_stimulus={'active':True}))


def evidence(hz=10, end=1000):
    row=demo_snapshot(hz,end)
    row.update(policy='ssvep-hdmi-experimental-v1',display_backend='hdmi_scan',display_page_id=4,
        display_timing=dict(schema='guardianloop-hdmi-latch-v1',source='hardware_latch_reports',
                            ready=True,error=None))
    return row


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.receiver=FakeReceiver();self.link=UnifiedLink(NetworkBridge(self.receiver))

    def test_explicit_motor_profile_keeps_quality_gates_and_reports_capability(self):
        self.receiver.motor_test=True
        row=self.link.step(player(),evidence(),10.)
        self.assertTrue(row['physical_output_enabled']);self.assertTrue(row['motor_gpio_enabled'])
        row=self.link.step(player(),None,10.1)
        self.assertEqual(row['direction'],'stop')
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'status';row.update(updated_monotonic=10.1)
            path.write_text(json.dumps(row))
            self.assertEqual(read_status(path,10.2)['state'],'unavailable')
            self.assertNotEqual(read_status(path,10.2,motor_test=True)['state'],'unavailable')

    def test_all_four_frequencies_use_existing_receiver_protocol(self):
        for hz,direction in [(8,'forward'),(10,'backward'),(12,'left'),(14,'right')]:
            with self.subTest(hz=hz):
                row=self.link.step(player(),evidence(hz,1000+50*len(self.receiver.calls)),10.)
                self.assertEqual(row['direction'],direction);self.assertTrue(row['sent'])
                self.assertFalse(row['physical_output_enabled']);self.assertFalse(row['speed_supported'])

    def test_page_changes_and_gates_send_only_stop(self):
        changes=[{'page':'speed'},{'page':'video'},{'mode':'scripted_hdmi_replay'},
                 {'force_stopped':True},{'alerts':{'fatigue':True}},{'direction_armed':False},
                 {'reading':True},{'eye_only':True},{'stimulus_enabled':False}]
        for change in changes:
            p=player();p['system'].update(change)
            self.assertEqual(self.link.step(p,evidence(),10.)['direction'],'stop')
        self.assertEqual(self.receiver.calls,['stop']*len(changes))

    def test_stale_display_and_wrong_page_never_send_direction(self):
        for p,s in [(player(8.),evidence()),(player(),dict(evidence(),display_page_id=8)),({},evidence())]:
            self.assertEqual(self.link.step(p,s,10.)['direction'],'stop')
        self.assertEqual(self.receiver.calls,['stop']*3)

    def test_old_eeg_and_test_only_plurality_are_not_motor_evidence(self):
        s=evidence();s['input']['age_seconds']=.6
        self.assertEqual(self.link.step(player(),s,10.)['direction'],'stop')
        s=evidence();s['accepted']=False
        p=player();p['system']['hdmi_stimulus']['votes']={'selected_hz':10}
        self.assertEqual(self.link.step(p,s,10.)['direction'],'stop')

    def test_unacknowledged_force_stop_wins_before_render_status_catches_up(self):
        p=player();command=dict(session_id=p['session_id'],id='new',action='force_stop')
        self.assertTrue(pending_stop(p,command))
        self.assertEqual(self.link.step(p,evidence(),10.,stop_pending=True)['direction'],'stop')
        p['command_receipt']={'id':'new','state':'applied'}
        self.assertFalse(pending_stop(p,command))
        self.assertFalse(pending_stop(p,dict(command,session_id='old')))

    def test_offline_does_not_replay_a_failed_direction_when_receiver_returns(self):
        self.receiver.fails=True
        self.assertEqual(self.link.step(player(),evidence(),10.)['state'],'offline')
        self.receiver.fails=False
        row=self.link.step(player(),evidence(),10.1)
        self.assertEqual(row['source_gate'],'waiting_for_new_window_after_link_failure')
        self.assertEqual(row['direction'],'stop')
        row=self.link.step(player(10.2),evidence(end=1050),10.2)
        self.assertEqual(row['direction'],'backward');self.assertTrue(row['sent'])

    def test_link_status_expiry_never_reports_old_delivery(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'status'
            self.assertEqual(read_status(path,10.)['state'],'unavailable')
            row=dict(policy=POLICY,updated_monotonic=10.,state='sent',physical_output_enabled=False)
            path.write_text(json.dumps(row))
            self.assertEqual(read_status(path,11.)['state'],'sent')
            self.assertEqual(read_status(path,14.)['state'],'unavailable')
            row['physical_output_enabled']=True;path.write_text(json.dumps(row))
            self.assertEqual(read_status(path,11.)['state'],'unavailable')

    def test_receiver_is_resolved_by_verified_mac_not_a_stale_dhcp_address(self):
        mac='30:ed:a0:a2:e4:24'
        rows=[dict(dst='192.168.50.44',lladdr=mac,state=['STALE']),
              dict(dst='192.168.50.72',lladdr='00:11:22:33:44:55',state=['REACHABLE'])]
        with patch('wheelchair_link.subprocess.check_output',return_value=json.dumps(rows)):
            self.assertEqual(receiver_address(mac),'http://192.168.50.44')
        rows[0]['state']=['FAILED']
        with patch('wheelchair_link.subprocess.check_output',return_value=json.dumps(rows)):
            self.assertIsNone(receiver_address(mac))

    def test_eye_navigation_brain_monitoring_and_receiver_share_one_page_owner(self):
        from guardianloop_system.core import SystemController
        from guardianloop_system.live_inputs import BrainInputs
        now=10.;controller=SystemController(now)
        for x in (.1,.5):
            controller.presented(controller.page_id,now);now+=1.3
            for _ in range(32):
                controller.gaze(dict(valid=True,x=x,monotonic_ns=int(now*1e9)),now)
                now+=.05
        self.assertEqual(controller.page,'drive')
        controller.presented(controller.page_id,now);now+=1.3
        self.assertTrue(controller.arm_virtual_direction(now))
        snapshot=evidence();snapshot['display_page_id']=controller.page_id
        inputs=BrainInputs(clock=lambda:now,fetch=lambda _: {},
                           hdmi_input=lambda *args:(snapshot,now,0,None))
        inputs.stop.set();inputs.thread.join();self.addCleanup(inputs.close)
        inputs.rows['status']=(dict(stale=False,fatigue=dict(valid=True,level=0,seq=1,
                                  emotion=dict(valid=True,class_name='calm'))),now,0,None)
        inputs.apply(controller,now)
        self.assertEqual(controller.direction,'backward')
        self.assertIn('fatigue',controller.monitor_labels)
        p=player(now);p['system'].update(controller.snapshot(now),mode='live_readonly_hdmi',
                                      eye_only=False,stimulus_enabled=True,hdmi_stimulus={'active':True})
        self.assertEqual(self.link.step(p,snapshot,now)['direction'],'backward')
        controller.gaze(dict(valid=True,x=.1,monotonic_ns=int(now*1e9)),now)
        self.assertEqual(controller.page,'drive')
        now+=.1
        inputs.rows['status']=(dict(stale=False,fatigue=dict(valid=True,level=2,seq=2,
                                  emotion={'valid':False})),now,0,None)
        inputs.apply(controller,now)
        p['updated_monotonic']=now;p['system'].update(controller.snapshot(now),mode='live_readonly_hdmi')
        self.assertEqual(self.link.step(p,snapshot,now)['direction'],'stop')
        self.assertEqual(self.receiver.calls[-1],'stop')


class ManualTests(unittest.TestCase):
    def setUp(self):
        self.receiver=FakeReceiver();self.manual=ManualControl('current')

    def test_applied_stop_survives_navigation_and_new_stop_still_wins(self):
        gate=PriorityStop();p=player()
        stop=dict(session_id=p['session_id'],id='stop-one',action='force_stop',queued_monotonic=9.)
        p['command_receipt']=dict(id='stop-one',state='applied')
        self.assertFalse(gate.pending(p,stop,{}))
        p['command_receipt']=dict(id='choose',state='applied')
        self.assertFalse(gate.pending(p,stop,{}))
        request=dict(self.request(),heartbeat_monotonic=10.,heartbeat_confirmed=True)
        manual=ManualControl('current',motor_test=True)
        manual.step(self.receiver,request,p,10.,gate.pending(p,stop,{}))
        self.assertEqual(manual.step(self.receiver,request,p,10.4,gate.pending(p,stop,{}))['direction'],'forward')
        new_stop=dict(stop,id='stop-two',queued_monotonic=10.5)
        self.assertTrue(gate.pending(p,new_stop,{}))
        row=manual.step(self.receiver,request,p,10.5,gate.pending(p,new_stop,{}))
        self.assertEqual(row['direction'],'stop');self.assertEqual(row['reason'],'priority_stop_pending')
        p['command_receipt']=dict(id='stop-two',state='applied')
        self.assertFalse(gate.pending(p,new_stop,{}))
        request['heartbeat_monotonic']=10.6
        self.assertEqual(manual.step(self.receiver,request,p,10.6,False)['direction'],'stop')

    def test_restart_recovers_consumed_stop_only_from_matching_later_navigation(self):
        gate=PriorityStop();p=player()
        stop=dict(session_id=p['session_id'],id='old-stop',action='force_stop',queued_monotonic=9.)
        nav=dict(session_id=p['session_id'],id='choose',action='choose',queued_monotonic=9.5)
        p['command_receipt']=dict(id='choose',state='applied',updated_monotonic=10.)
        self.assertTrue(gate.pending(p,stop,{}))
        for change in ({'queued_monotonic':8.},{'queued_monotonic':float('nan')},
                       {'id':'unprocessed'},{'session_id':'foreign'}):
            self.assertTrue(gate.pending(p,stop,dict(nav,**change)))
        self.assertFalse(gate.pending(p,stop,nav))
        p['command_receipt']=dict(id='another',state='applied')
        self.assertFalse(gate.pending(p,stop,dict(nav,id='another',queued_monotonic=10.)))
        self.assertTrue(PriorityStop().pending(p,dict(stop,id='fresh',queued_monotonic=11.),nav))

    def test_explicit_stop_is_not_reported_as_phone_heartbeat_loss(self):
        manual=ManualControl('current',motor_test=True)
        request=dict(self.request('stop'),heartbeat_monotonic=10.)
        self.assertEqual(manual.step(self.receiver,request,{},10.8)['reason'],'manual_stop')

    def test_motor_manual_continues_with_heartbeat_and_stops_without_auto_resume(self):
        self.receiver.motor_test=True;manual=ManualControl('current',motor_test=True)
        request=dict(self.request(),heartbeat_monotonic=10.,heartbeat_confirmed=True)
        row=manual.step(self.receiver,request,{},10.)
        self.assertTrue(row['physical_output_enabled']);self.assertTrue(row['motor_gpio_enabled'])
        self.assertEqual(row['state'],'preparing')
        for step in range(4,1201):
            now=10.+step/10;request['heartbeat_monotonic']=now
            row=manual.step(self.receiver,request,{},now)
            self.assertEqual(row['direction'],'forward');self.assertTrue(row['sent'])
        self.assertEqual(self.receiver.calls[:3],['stop','manual_arm','forward'])
        self.assertEqual(self.receiver.calls.count('manual_arm'),1)
        row=manual.step(self.receiver,request,{},130.76)
        self.assertEqual(row['direction'],'stop')
        request['heartbeat_monotonic']=131.
        self.assertEqual(manual.step(self.receiver,request,{},131.)['direction'],'stop')
        self.assertEqual(self.receiver.calls.count('manual_arm'),1)

    def test_manual_bootstrap_requires_foreground_confirmation_and_survives_no_old_intent(self):
        manual=ManualControl('current',motor_test=True)
        request=dict(self.request(),heartbeat_monotonic=10.,heartbeat_confirmed=False)
        manual.step(self.receiver,request,{},10.)
        self.assertEqual(manual.step(self.receiver,request,{},10.4)['state'],'preparing')
        self.assertNotIn('manual_arm',self.receiver.calls)
        self.assertEqual(manual.step(self.receiver,request,{},10.76)['direction'],'stop')
        manual=ManualControl('current',motor_test=True,ignore_id='one')
        request.update(heartbeat_confirmed=True,heartbeat_monotonic=10.4)
        self.assertIsNone(manual.step(self.receiver,request,{},10.4))

    def test_manual_direction_change_stops_before_fresh_arm_and_failure_cannot_rearm(self):
        manual=ManualControl('current',motor_test=True)
        request=dict(self.request(),heartbeat_monotonic=10.,heartbeat_confirmed=True)
        manual.step(self.receiver,request,{},10.);manual.step(self.receiver,request,{},10.4)
        reverse=dict(self.request('backward','two',10.5),heartbeat_monotonic=10.5,heartbeat_confirmed=True)
        self.assertEqual(manual.step(self.receiver,reverse,{},10.5)['state'],'preparing')
        self.assertEqual(self.receiver.calls[-1],'stop')
        manual.step(self.receiver,reverse,{},10.8);self.assertEqual(self.receiver.calls[-1],'stop')
        self.receiver.fails=True
        self.assertEqual(manual.step(self.receiver,reverse,{},10.9)['state'],'offline')
        self.receiver.fails=False;reverse['heartbeat_monotonic']=11.
        self.assertEqual(manual.step(self.receiver,reverse,{},11.)['direction'],'stop')
        self.assertEqual(self.receiver.calls.count('manual_arm'),2)

    def request(self,value='forward',ident='one',stamp=10.):
        return dict(boot='current',id=ident,value=value,queued_monotonic=stamp)

    def test_phone_directions_use_receiver_and_one_pulse_never_renews(self):
        for direction in ('forward','backward','left','right'):
            receiver=FakeReceiver();manual=ManualControl('current');request=self.request(direction)
            row=manual.step(receiver,request,{},10.)
            self.assertTrue(row['sent']);self.assertEqual(row['direction'],direction)
            manual.step(receiver,request,{},10.1)
            row=manual.step(receiver,request,{},10.26)
            self.assertEqual(receiver.calls,[direction,'stop'])
            self.assertEqual(row['direction'],'stop');self.assertEqual(row['control_mode'],'manual')
            self.assertFalse(row['physical_output_enabled'])

    def test_phone_stop_persists_until_explicit_ssvep_request(self):
        self.manual.step(self.receiver,self.request('stop'),{},10.)
        self.assertEqual(self.manual.step(self.receiver,{},player(),11.)['direction'],'stop')
        self.manual.step(self.receiver,self.request('ssvep','two',11.),player(),11.)
        self.assertIsNone(self.manual.step(self.receiver,{},player(),11.1))
        self.assertEqual(self.receiver.calls,['stop','stop'])

    def test_never_unlocks_receiver_without_local_permit(self):
        from bench_network_bridge import BenchReceiver
        from test_network_bridge import Opener,Response,bench_state
        receiver=BenchReceiver('http://192.168.50.72','a'*64)
        receiver.opener=Opener([Response(bench_state(armed=False))])
        row=self.manual.step(receiver,self.request(),{},10.)
        self.assertEqual(row['state'],'permit_required');self.assertFalse(row['sent'])
        self.assertEqual(len(receiver.opener.requests),1)
        self.assertEqual(receiver.opener.requests[0].get_method(),'GET')

    def test_manual_does_not_accept_motor_enabled_firmware(self):
        from bench_network_bridge import BenchReceiver
        from test_network_bridge import Opener,Response,bench_state
        receiver=BenchReceiver('http://192.168.50.72','a'*64)
        receiver.opener=Opener([Response(bench_state(motor_gpio_enabled=True))])
        row=self.manual.step(receiver,self.request(),{},10.)
        self.assertFalse(row['sent']);self.assertEqual(row['direction'],'stop')
        self.assertEqual(len(receiver.opener.requests),1)

    def test_stale_or_previous_boot_requests_never_replay(self):
        for command in [dict(self.request(),boot='old'),self.request(stamp=8.),
                        dict(self.request(),value={}),dict(self.request(),queued_monotonic=float('nan'))]:
            self.assertIsNone(self.manual.step(self.receiver,command,{},10.))
        self.assertEqual(self.receiver.calls,[])

    def test_expired_pulse_fatigue_and_force_stop_only_submit_stop(self):
        for command,p,now,pending in [(self.request(),{},10.3,False),
                (self.request(),dict(system={'alerts':{'fatigue':True}}),10.,False),
                (self.request(),{},10.,True)]:
            manual=ManualControl('current');receiver=FakeReceiver()
            row=manual.step(receiver,command,p,now,pending)
            self.assertEqual(row['direction'],'stop');self.assertEqual(receiver.calls,['stop'])

    def test_offline_request_cannot_replay_after_reconnection(self):
        command=self.request()
        self.assertFalse(self.manual.step(None,command,{},10.)['sent'])
        row=self.manual.step(self.receiver,command,{},10.1)
        self.assertEqual(row['direction'],'stop');self.assertEqual(self.receiver.calls,[])


if __name__=='__main__':unittest.main()
