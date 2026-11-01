import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from guardianloop_system.core import SystemController
from guardianloop_system.live_inputs import BrainInputs,EyeInputs
from guardianloop_system.media_library import MediaLibrary,RatingWriter
from wheelchair_ssvep.dry_run_bridge import demo_snapshot


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.now=10.;self.system=SystemController(self.now)
        self.inputs=BrainInputs(clock=lambda:self.now,fetch=lambda _:{});self.inputs.stop.set();self.inputs.thread.join()
        self.addCleanup(self.inputs.close)

    def put(self,payload):self.inputs.rows['status']=(payload,self.now,.01,None)

    def test_response_published_after_loop_timestamp_is_still_fresh(self):
        loop_time=self.now
        self.now+=.05
        self.put(dict(stale=False,fatigue=dict(seq=1,valid=True,level='low',emotion={'valid':False})))
        self.now+=.05
        self.assertEqual(self.inputs.snapshot(loop_time)['state'],'live')

    def test_delayed_loop_timestamp_cannot_keep_expired_response_live(self):
        loop_time=self.now
        self.put(dict(stale=False,fatigue=dict(seq=1,valid=True,level='low',emotion={'valid':False})))
        self.now+=1.6
        self.assertEqual(self.inputs.snapshot(loop_time)['state'],'no_data')

    def test_truly_future_response_is_rejected(self):
        self.inputs.rows['status']=(dict(stale=False,fatigue=dict(valid=True)),self.now+.2,.01,None)
        self.assertEqual(self.inputs.snapshot(self.now)['state'],'no_data')

    def test_new_independent_input_does_not_false_disarm_direction(self):
        loop_time=self.now
        self.system._enter('drive',loop_time);self.system.direction_armed=True
        self.now+=.05
        hdmi=dict(source='live',state_owner='acquisition',control_enabled=False,input=dict(ready=True))
        self.inputs.rows['ssvep-hdmi']=(hdmi,self.now,.01,None)
        self.put(dict(stale=True,fatigue={'valid':False}))
        self.now+=.05
        self.inputs.apply(self.system,loop_time)
        self.assertTrue(self.system.direction_armed)

    def test_no_data_and_transport_stale_revoke_old_results(self):
        self.system.monitor('fatigue','low',self.now,source='live_model_candidate',qualified=True)
        self.put(dict(stale=True,fatigue=dict(valid=True,level='high')))
        self.inputs.apply(self.system,self.now)
        self.assertFalse(self.system.monitor_labels);self.assertNotIn('fatigue',self.system.alerts)
        self.now+=2;self.assertEqual(self.inputs.snapshot(self.now)['state'],'no_data')

    def test_acquisition_pause_retracts_even_fresh_results_and_direction(self):
        owner=[(40,10)];self.inputs.availability=lambda:owner[0]
        self.inputs._sync_acquisition()
        self.put(dict(stale=False,fatigue=dict(seq=1,valid=True,level='low',emotion=dict(valid=True,label='boring'))))
        self.inputs.apply(self.system,self.now);self.assertTrue(self.system.monitor_labels)
        self.system._enter('drive',self.now);self.system.direction='left';self.system.direction_armed=True
        self.inputs.hdmi_input=lambda *args:(_ for _ in ()).throw(AssertionError('Old HDMI result consumed'))
        owner[0]=None
        view=self.inputs.apply(self.system,self.now+.01)
        self.assertEqual(view['state'],'no_data');self.assertFalse(view['emotion']['valid'])
        self.assertFalse(self.system.monitor_labels);self.assertEqual(self.system.direction,'stop')
        self.assertFalse(self.system.direction_armed);self.assertFalse(self.inputs.rows)

    def test_restart_cannot_reuse_cached_response_or_sequence(self):
        owner=[(40,10)];self.inputs.availability=lambda:owner[0];self.inputs._sync_acquisition()
        self.put(dict(stale=False,fatigue=dict(seq=1,valid=True,level='low',emotion={'valid':False})))
        self.inputs.apply(self.system,self.now);owner[0]=(41,20)
        self.assertEqual(self.inputs.apply(self.system,self.now+.01)['state'],'no_data')
        self.assertIsNone(self.inputs.last_seq)
        self.put(dict(stale=False,fatigue=dict(seq=1,valid=True,level='low',emotion={'valid':False})))
        self.assertEqual(self.inputs.apply(self.system,self.now+.02)['state'],'live')
        self.assertIn('fatigue',self.system.monitor_labels)

    def test_response_crossing_owner_change_is_discarded(self):
        owner=[(40,10)];self.inputs.availability=lambda:owner[0];self.inputs._sync_acquisition()
        def fetch(endpoint):
            owner[0]=None;self.inputs.stop.set()
            return dict(stale=False,fatigue=dict(valid=True))
        self.inputs.fetch=fetch;self.inputs.stop.clear();self.inputs._run()
        self.assertFalse(self.inputs.rows)

    def test_independent_fresh_ssvep_does_not_need_fatigue_calibration(self):
        self.system._enter('drive',self.now);self.system.direction_armed=True
        hdmi=dict(source='live',state_owner='acquisition',control_enabled=False,input=dict(ready=True))
        self.inputs.rows['ssvep-hdmi']=(hdmi,self.now,.01,None)
        self.put(dict(stale=True,fatigue={'valid':False}))
        self.inputs.apply(self.system,self.now)
        self.assertTrue(self.system.direction_armed)
        self.assertEqual(self.system.direction,'stop')
        self.inputs.apply(self.system,self.now+2)
        self.assertFalse(self.system.direction_armed)

    def test_live_mood_is_proxy_and_offline_never_accepted(self):
        f=dict(valid=True,seq=7,level='low',emotion=dict(valid=True,class_name='horror'))
        self.put(dict(stale=False,fatigue=f));view=self.inputs.apply(self.system,self.now)
        self.assertEqual(view['state'],'live');self.assertIn('mood',self.system.alerts)
        self.assertFalse(self.system.snapshot(self.now)['physical_output_enabled'])
        f['offline']=True;self.inputs.apply(self.system,self.now+.1)
        self.assertFalse(self.system.monitor_labels)

    def test_stale_stream_keeps_only_calibration_metadata(self):
        self.put(dict(stale=True,fatigue=dict(valid=True,level='high',score=.9,
            calibration_retained=True,calibration_current=15,calibration_total=15,
            emotion=dict(valid=True,class_name='horror'))))
        view=self.inputs.apply(self.system,self.now)
        self.assertFalse(view['fatigue']['valid']);self.assertFalse(view['emotion']['valid'])
        self.assertEqual(view['fatigue']['calibration_current'],15)
        self.assertNotIn('score',view['fatigue']);self.assertFalse(self.system.monitor_labels)
        self.assertNotIn('calibration_current',self.inputs.snapshot(self.now+2)['fatigue'])

    def test_ssvep_requires_existing_gate_and_producer_freshness(self):
        self.system._enter('drive',self.now);self.system.presented(self.system.page_id,self.now)
        self.now+=1.3;self.system.arm_virtual_direction(self.now)
        self.put(dict(stale=False,fatigue=dict(seq=1,valid=True,level='low',emotion={'valid':False})))
        data=demo_snapshot(policy='ssvep-hdmi-experimental-v1',display_backend='hdmi_scan',
            display_page_id=self.system.page_id,display_timing=dict(schema='guardianloop-hdmi-latch-v1',
                source='hardware_latch_reports',ready=True,error=None))
        self.inputs.hdmi_input=lambda page,now:(data,self.now,.01,None)
        self.inputs.apply(self.system,self.now);self.assertEqual(self.system.direction,'forward')
        self.inputs.apply(self.system,self.now+.6);self.assertEqual(self.system.direction,'stop')

    def test_browser_session_cannot_supply_a_native_hdmi_selection(self):
        self.system._enter('drive',self.now);self.system.presented(self.system.page_id,self.now)
        self.now+=1.3;self.system.arm_virtual_direction(self.now)
        self.put(dict(stale=False,fatigue=dict(seq=1,valid=True,level='low',emotion={'valid':False})))
        self.inputs.rows['ssvep-free']=(demo_snapshot(),self.now,.01,None)
        self.inputs.apply(self.system,self.now)
        self.assertEqual(self.system.direction,'stop')

    def test_speed_precedes_direction_and_restart_at_lowest(self):
        self.system.presented(self.system.page_id,self.now);self.now+=1.3
        self.system.speed_level=3;self.system.choose(0,self.now)
        self.assertEqual(self.system.page,'speed');self.assertEqual(self.system.speed_level,1)
        self.assertFalse(self.system.arm_virtual_direction(self.now))

    def test_invalid_results_are_revoked_even_when_sequence_did_not_advance(self):
        f=dict(seq=9,valid=True,level='normal',emotion=dict(valid=True,label='boring'))
        self.put(dict(stale=False,fatigue=f));self.inputs.apply(self.system,self.now)
        self.assertIn('emotion',self.system.monitor_labels)
        f.update(valid=False,emotion={'valid':False})
        self.inputs.apply(self.system,self.now+.1)
        self.assertFalse(self.system.monitor_labels);self.assertNotIn('mood',self.system.alerts)

    def test_board_severe_level_causes_virtual_stop(self):
        self.put(dict(stale=False,fatigue=dict(seq=10,valid=True,level='severe',emotion={'valid':False})))
        self.inputs.apply(self.system,self.now)
        self.assertIn('fatigue',self.system.alerts);self.assertEqual(self.system.direction,'stop')

    def test_invalid_emotion_revokes_song_prompt_without_new_sequence(self):
        f=dict(seq=15,valid=True,level='normal',emotion=dict(valid=True,label='horror'))
        self.put(dict(stale=False,fatigue=f));self.inputs.apply(self.system,self.now)
        self.assertEqual(self.system.page,'music_offer')
        f['emotion']={'valid':False};self.inputs.apply(self.system,self.now+.1)
        self.assertEqual(self.system.page,'home');self.assertNotIn('mood',self.system.alerts)

    def test_disconnect_clears_model_mood_but_keeps_latched_safety_warning(self):
        f=dict(seq=12,valid=True,level='severe',emotion=dict(valid=True,label='horror'))
        self.put(dict(stale=False,fatigue=f));self.inputs.apply(self.system,self.now)
        self.assertIn('mood',self.system.alerts);self.assertIn('fatigue',self.system.alerts)
        self.inputs.apply(self.system,self.now+1.6)
        self.assertFalse(self.system.monitor_labels);self.assertNotIn('mood',self.system.alerts)
        self.assertIn('fatigue',self.system.alerts)
        self.assertEqual(self.system.direction,'stop');self.assertFalse(self.system.direction_armed)

    def test_model_mood_expires_even_if_controller_ticks_before_adapter(self):
        self.put(dict(stale=False,fatigue=dict(seq=13,valid=True,level='normal',
            emotion=dict(valid=True,label='horror'))))
        self.inputs.apply(self.system,self.now);self.system.tick(self.now+2.1)
        self.inputs.apply(self.system,self.now+2.1)
        self.assertFalse(self.system.monitor_labels);self.assertNotIn('mood',self.system.alerts)

    def test_two_library_instances_do_not_overwrite_each_others_ratings(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'ratings.json';a=MediaLibrary(p);b=MediaLibrary(p)
            rows=[dict(id=i,name=i,cache=temp,download=str(p),source='SD_card') for i in ('a','b')]
            a.replace(rows);b.replace(rows);a.rate('a','好');b.rate('b','厌倦')
            self.assertEqual([r['rating'] for r in a.snapshot()],['好','厌倦'])

    def test_ratings_persist_by_id_not_playlist_position(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'ratings.json';lib=MediaLibrary(p)
            rows=[dict(id='a',name='A',cache=temp,download=str(p),source='SD_card'),
                  dict(id='b',name='B',cache=temp,download=str(p),source='phone_upload')]
            lib.replace(rows);writer=RatingWriter(lib);writer.submit('a','好');writer.close()
            reopened=MediaLibrary(p);reopened.replace(rows[::-1])
            self.assertEqual(reopened.snapshot()[1]['rating'],'好')
            self.assertFalse(reopened.snapshot()[1]['phone_file_saved'])
            with self.assertRaises(ValueError):reopened.rate('../unknown','好')


class EyeInputTests(unittest.TestCase):
    def setUp(self):
        self.now=10.;self.system=SystemController(self.now)
        self.system.presented(self.system.page_id,self.now)
        self.now+=1.3
        with patch('calibration_worker.Worker') as factory:
            self.eye=EyeInputs(Path('unused'))
        self.worker=factory.return_value;self.worker.done=False
        self.eye.ready=True;self.eye.guide.phase='selection'

    def test_stale_native_packet_cannot_refresh_eye_validity(self):
        self.worker.poll.return_value=[dict(kind='horizontal_gaze',valid=True,x=.1,monotonic_ns=1)]
        self.eye.poll(self.system,self.now)
        self.assertFalse(self.eye.snapshot(self.now)['valid'])
        self.assertEqual(self.eye.stale_samples,1)
        self.assertEqual(self.system.page,'home')

    def test_native_error_revokes_selected_and_half_finished_actions(self):
        self.system.selection.selected=0;self.system.selection.progress=.9
        self.system.direction='left';self.system.direction_armed=True
        self.system.mi_first={'confirmed_at':self.now}
        self.worker.poll.return_value=[dict(kind='error',code=-1),
            dict(kind='horizontal_gaze',valid=True,x=.1,monotonic_ns=int(self.now*1e9))]
        self.eye.poll(self.system,self.now)
        self.assertFalse(self.eye.snapshot(self.now)['valid'])
        self.assertEqual(self.system.selection.selected,-1)
        self.assertEqual(self.system.selection.progress,0)
        self.assertEqual(self.system.direction,'stop');self.assertFalse(self.system.direction_armed)
        self.assertIsNone(self.system.mi_first);self.assertEqual(self.system.page,'home')

    def test_native_error_is_terminal_and_exposes_manual_reconnection(self):
        self.system.last_selection={'page_id':0,'region':0}
        self.worker.poll.return_value=[dict(kind='error',code=-1),
            dict(kind='ready'),dict(kind='direction_ready',trained=True)]
        view=self.eye.poll(self.system,self.now)
        snapshot=self.eye.snapshot(self.now)
        self.assertEqual(view.phase,'failed');self.assertIn('PS_KEY0 重连',view.detail)
        self.assertFalse(snapshot['connected']);self.assertFalse(snapshot['control_enabled'])
        self.assertTrue(snapshot['reconnect_required']);self.assertEqual(snapshot['reconnect_action'],'eye_start')
        self.assertIsNone(self.system.last_selection)
        self.worker.poll.return_value=[dict(kind='ready'),dict(kind='error',code=-4)]
        self.eye.poll(self.system,self.now+.1)
        self.assertEqual(self.eye.error,'native_exit_-1')
        self.assertEqual(len(self.system.events),1)

    def test_silent_transport_requires_reconnection_without_reusing_old_gaze(self):
        self.worker.poll.return_value=[dict(kind='horizontal_gaze',valid=True,x=.5,monotonic_ns=int(self.now*1e9))]
        self.eye.poll(self.system,self.now)
        self.worker.poll.return_value=[]
        view=self.eye.poll(self.system,self.now+3.1)
        self.assertEqual(view.phase,'failed');self.assertEqual(self.eye.error,'native_silent')
        self.assertTrue(self.eye.snapshot(self.now+3.1)['reconnect_required'])
        self.assertIsNone(self.eye.last_valid)

    def test_live_quality_with_no_visible_eyes_is_not_transport_loss(self):
        self.worker.poll.return_value=[dict(kind='quality',samples=20,left=0,right=0,
            pupil_left=0,pupil_right=0,distance_mm=0.)]
        for step in range(5):
            self.eye.poll(self.system,self.now+step)
        self.assertIsNone(self.eye.error);self.assertFalse(self.eye.snapshot(self.now+4)['reconnect_required'])

    def test_new_connection_cannot_inherit_previous_calibration_or_confirmation(self):
        self.worker.poll.return_value=[dict(kind='error',code=-1)]
        self.eye.poll(self.system,self.now);self.eye.close()
        with patch('calibration_worker.Worker') as factory:
            replacement=EyeInputs(Path('unused'))
        factory.return_value.done=False
        factory.return_value.poll.return_value=[dict(kind='ready')]
        replacement.poll(self.system,self.now+.1)
        self.assertEqual(replacement.guide.phase,'positioning')
        self.assertIsNone(replacement.entry);self.assertFalse(replacement.ready)
        self.assertFalse(replacement.control_enabled);self.assertIsNone(replacement.error)

    def test_fresh_packets_expire_and_clean_exit_is_not_live(self):
        self.worker.poll.return_value=[dict(kind='horizontal_gaze',valid=True,x=.5,monotonic_ns=int(self.now*1e9))]
        self.eye.poll(self.system,self.now)
        self.assertTrue(self.eye.snapshot(self.now)['valid'])
        self.assertFalse(self.eye.snapshot(self.now+.31)['valid'])
        self.worker.poll.return_value=[];self.worker.done=True
        self.eye.poll(self.system,self.now+.31)
        self.assertFalse(self.eye.snapshot(self.now+.31)['connected'])
        self.assertEqual(self.eye.error,'native_stopped')

    def test_position_confirmation_needs_fresh_both_eye_telemetry(self):
        self.eye.ready=False
        self.worker.poll.return_value=[dict(kind='ready')]
        self.eye.poll(self.system,self.now)
        self.assertEqual(self.eye.guide.phase,'positioning')
        self.assertFalse(self.eye.confirm_position(self.now))
        quality=dict(kind='quality',samples=20,left=20,right=19,
            pupil_left=20,pupil_right=0,distance_mm=503.)
        self.worker.poll.return_value=[quality]
        view=self.eye.poll(self.system,self.now)
        self.assertIn('50.3 cm',view.tracking[0])
        self.assertIn('95%',view.tracking[0])
        self.assertFalse(self.eye.confirm_position(self.now))
        quality['pupil_right']=19
        self.eye.poll(self.system,self.now)
        self.assertFalse(self.eye.confirm_position(self.now+1.6))
        self.eye.poll(self.system,self.now+1.6)
        self.assertTrue(self.eye.confirm_position(self.now+1.6))
        self.assertEqual(self.eye.guide.phase,'prepare')

    def test_three_correct_selections_gate_menu_and_preserve_held_lock(self):
        self.worker.poll.return_value=[dict(kind='direction_ready',trained=True)]
        view=self.eye.poll(self.system,self.now)
        self.assertFalse(self.eye.control_enabled)
        self.assertEqual(self.eye.guide.phase,'verification')
        for region in (1,0,2):
            self.eye.presented(view,self.now)
            for i in range(32):
                now=self.now+1.3+i*.05
                self.worker.poll.return_value=[dict(kind='horizontal_gaze',valid=True,
                    x=(region+.5)/3,monotonic_ns=int(now*1e9))]
                view=self.eye.poll(self.system,now)
            self.now=now+.2
            self.assertEqual(self.system.page,'home')
        self.assertTrue(self.eye.control_enabled)
        self.assertTrue(self.eye.snapshot(self.now)['quick_check']['passed'])
        self.assertEqual(self.system.selection.locked,2)
        self.system.presented(self.system.page_id,self.now)
        for i in range(40):
            now=self.now+1.3+i*.05
            self.worker.poll.return_value=[dict(kind='horizontal_gaze',valid=True,
                x=5/6,monotonic_ns=int(now*1e9))]
            self.eye.poll(self.system,now)
        self.assertEqual(self.system.page,'home')

    def test_wrong_quick_selection_fails_without_menu_action(self):
        self.worker.poll.return_value=[dict(kind='direction_ready',trained=True)]
        view=self.eye.poll(self.system,self.now);self.eye.presented(view,self.now)
        for i in range(32):
            now=self.now+1.3+i*.05
            self.worker.poll.return_value=[dict(kind='horizontal_gaze',valid=True,
                x=.1,monotonic_ns=int(now*1e9))]
            self.eye.poll(self.system,now)
        self.assertEqual(self.eye.guide.phase,'failed')
        self.assertFalse(self.eye.control_enabled)
        self.assertEqual(self.eye.error,'quick_check_wrong_region')
        self.assertFalse(self.eye.snapshot(now)['quick_check']['passed'])
        self.assertEqual(self.system.page,'home')


if __name__=='__main__':unittest.main()
