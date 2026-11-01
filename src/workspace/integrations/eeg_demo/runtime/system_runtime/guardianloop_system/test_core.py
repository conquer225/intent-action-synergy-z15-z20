import unittest

from guardianloop_system.core import SystemController
from wheelchair_ssvep.dry_run_bridge import demo_snapshot


class SystemTests(unittest.TestCase):
    def setUp(self):
        self.now=10.;self.system=SystemController(self.now);self.ready()

    def ready(self):
        self.system.presented(self.system.page_id,self.now)
        self.now+=1.3

    def choose(self,zone):
        self.assertTrue(self.system.choose(zone,self.now));self.ready()

    def mi(self,ident,label,start,end,session='s',**changes):
        self.now+=.2
        event=dict(id=ident,session=session,label=label,window_start=start,window_end=end,
            received_at=self.now,accepted=True,quality_ready=True)
        event.update(changes)
        return self.system.mi(event,self.now)

    def drive(self):
        self.choose(0);self.assertEqual(self.system.page,'speed')
        self.assertEqual(self.system.speed_level,1)
        self.choose(1);self.assertEqual(self.system.page,'drive')

    def test_video_nav_and_rate_return_to_video(self):
        self.system.video_count=3;self.choose(2);self.choose(0)
        self.assertEqual(self.system.page,'video')
        self.choose(0);self.assertEqual(self.system.page,'video_nav')
        self.choose(2);self.assertEqual(self.system.video_index,1);self.assertEqual(self.system.page,'video')
        self.choose(2);self.choose(0);self.assertEqual(self.system.rating,'好')
        self.assertEqual(self.system.page,'video')
        self.assertFalse(self.system.choose(1,self.now));self.assertEqual(self.system.page,'video')

    def test_selection_receipt_belongs_to_executed_page_not_held_region(self):
        origin=self.system.page_id
        self.choose(1)
        self.assertEqual(self.system.page,'speech')
        self.assertEqual(self.system.last_selection['page_id'],origin)
        self.assertNotEqual(self.system.last_selection['page_id'],self.system.page_id)
        self.choose(0)
        self.assertEqual(self.system.phrase,'我想喝水')
        self.assertEqual(self.system.last_selection['page_id'],self.system.page_id)
        self.assertEqual(self.system.last_selection['region'],0)
        receipt=dict(self.system.last_selection)
        self.assertFalse(self.system.choose(2,self.now-10))
        self.assertEqual(self.system.last_selection,receipt)

    def test_holding_centre_after_navigation_does_not_claim_another_action(self):
        for i in range(32):
            stamp=self.now+i*.05
            self.system.gaze(dict(valid=True,x=.5,monotonic_ns=int(stamp*1e9)),stamp)
        self.assertEqual(self.system.page,'speech');receipt=dict(self.system.last_selection)
        self.now=stamp+.1;self.ready()
        for i in range(45):
            stamp=self.now+i*.05
            self.assertFalse(self.system.gaze(dict(valid=True,x=.5,monotonic_ns=int(stamp*1e9)),stamp))
        self.assertEqual(self.system.page,'speech')
        self.assertEqual(self.system.last_selection,receipt)

    def test_speed_virtual_only_and_page_switch_stops_direction(self):
        self.drive();self.assertTrue(self.system.arm_virtual_direction(self.now))
        self.system.ssvep(demo_snapshot(8),self.now)
        self.assertEqual(self.system.direction,'forward')
        self.choose(1);self.assertEqual(self.system.page,'home');self.assertEqual(self.system.direction,'stop')
        self.choose(0);self.assertEqual(self.system.page,'speed')
        self.choose(0);self.assertEqual(self.system.speed_level,2)
        self.choose(1);self.assertEqual(self.system.page,'drive')
        snap=self.system.snapshot(self.now)
        self.assertFalse(snap['direction_armed']);self.assertFalse(snap['hardware_speed_supported'])
        self.assertFalse(snap['physical_output_enabled'])

    def test_direction_centre_gaze_returns_home_and_corners_do_not_select_menus(self):
        self.drive()
        for x in (.12,.88):
            for _ in range(45):
                self.now+=.05
                self.system.gaze(dict(valid=True,x=x,monotonic_ns=int(self.now*1e9)),self.now)
            self.assertEqual(self.system.page,'drive')
        for _ in range(60):
            self.now+=.05
            self.system.gaze(dict(valid=True,x=.5,monotonic_ns=int(self.now*1e9)),self.now)
        self.assertEqual(self.system.page,'home')
        self.assertEqual(self.system.direction,'stop')
        self.assertFalse(self.system.direction_armed)

    def test_video_navigation_centre_returns_home_without_changing_video(self):
        self.system.video_count=3;self.choose(2);self.choose(0);self.choose(0)
        self.assertEqual(self.system.page,'video_nav')
        self.assertEqual(self.system.labels(),('上一条','返回主页','下一条'))
        self.choose(1)
        self.assertEqual(self.system.page,'home');self.assertEqual(self.system.video_index,0)

    def test_direction_expires_without_new_evidence(self):
        self.drive();self.system.arm_virtual_direction(self.now)
        self.system.ssvep(demo_snapshot(),self.now);self.system.tick(self.now+.31)
        self.assertEqual(self.system.direction,'stop');self.assertFalse(self.system.direction_armed)

    def test_stale_or_invalid_ssvep_requests_stop(self):
        self.drive();self.system.arm_virtual_direction(self.now)
        for snapshot in (None,demo_snapshot(accepted=False),demo_snapshot(frame_ok=False)):
            self.system.ssvep(snapshot,self.now);self.assertEqual(self.system.direction,'stop')

    def test_two_right_requires_neutral_and_distinct_nonoverlapping_windows(self):
        self.choose(2);self.choose(0)
        self.assertFalse(self.mi('a','right',0,500))
        self.assertFalse(self.mi('b','right',500,1000))
        self.assertFalse(self.mi('a','right',0,500))
        self.assertFalse(self.mi('n','neutral',500,1000))
        self.assertFalse(self.mi('overlap','right',400,900))
        self.assertFalse(self.mi('overlap-neutral','right',600,1100))
        self.assertTrue(self.mi('c','right',1000,1500))
        self.assertEqual(self.system.page,'home');self.assertTrue(self.system.exited)
        self.assertFalse(self.system.direction_armed)

    def test_mi_session_change_gap_and_bad_quality_clear_pair(self):
        self.mi('a','right',0,500);self.mi('n','neutral',500,1000)
        self.assertFalse(self.mi('b','right',1000,1500,session='new'))
        self.system.signal_lost(self.now)
        self.assertFalse(self.system.mi_first)

    def test_page_transition_discards_half_finished_mi_exit(self):
        self.mi('a','right',0,500);self.mi('n','neutral',500,1000)
        self.choose(2)
        self.assertFalse(self.system.mi_first)
        self.assertFalse(self.mi('b','right',1000,1500))
        self.assertFalse(self.system.exited)
        self.mi('c','right',1500,2000);self.mi('bad','neutral',2000,2500,quality_ready=False)
        self.assertFalse(self.system.mi_first)

    def test_mi_pair_times_out_and_stale_candidate_cannot_exit(self):
        self.mi('a','right',0,500);self.system.tick(self.now+9);self.now+=9
        self.assertFalse(self.system.mi_first)
        self.assertFalse(self.mi('b','right',500,1000,received_at=self.now-2))
        self.assertFalse(self.system.exited)

    def test_page_presented_reading_and_gaze_hold_dont_cascade(self):
        self.system._enter('media',self.now)
        self.now+=10
        self.assertFalse(self.system.choose(0,self.now))
        self.ready()
        for i in range(100):
            stamp=self.now+i*.02
            self.system.gaze(dict(valid=True,x=.12,monotonic_ns=int(stamp*1e9)),stamp)
        self.assertEqual(self.system.page,'video')
        self.now+=2;self.ready()
        for i in range(100):
            stamp=self.now+i*.02
            self.system.gaze(dict(valid=True,x=.12,monotonic_ns=int(stamp*1e9)),stamp)
        self.assertEqual(self.system.page,'video')

    def test_video_centre_is_not_a_control_and_stale_gaze_rejected(self):
        self.choose(2);self.choose(0)
        for i in range(100):
            stamp=self.now+i*.02
            self.assertFalse(self.system.gaze(dict(valid=True,x=.5,monotonic_ns=int(stamp*1e9)),stamp))
        self.assertFalse(self.system.gaze(dict(valid=True,x=.1,monotonic_ns=1),self.now+2))

    def test_stable_centre_viewing_rearms_a_side_without_selecting(self):
        self.choose(2);self.choose(0);self.system.selection.locked=0
        for i in range(30):
            stamp=self.now+i*.02
            self.assertFalse(self.system.gaze(dict(valid=True,x=.5,monotonic_ns=int(stamp*1e9)),stamp))
        self.assertEqual(self.system.page,'video');self.assertEqual(self.system.selection.locked,-1)
        self.now+=.6
        for i in range(80):
            stamp=self.now+i*.02
            self.system.gaze(dict(valid=True,x=.1,monotonic_ns=int(stamp*1e9)),stamp)
        self.assertEqual(self.system.page,'video_nav')

    def test_gameemo_label_does_not_assert_bad_mood(self):
        self.system.monitor('emotion','negative',self.now,source='GAMEEMO_condition',qualified=True)
        self.assertNotIn('mood',self.system.alerts);self.assertEqual(self.system.page,'home')
        self.system.monitor('emotion','poor',self.now,source='user_report',qualified=True)
        self.assertEqual(self.system.page,'music_offer')
        self.assertFalse(self.system.snapshot(self.now)['audio_output'])

    def test_model_mood_reference_needs_quality_and_does_not_take_over_driving(self):
        self.system.monitor('emotion','horror',self.now,source='GAMEEMO_condition',qualified=False)
        self.assertNotIn('mood',self.system.alerts)
        self.drive()
        self.system.monitor('emotion','horror',self.now,source='GAMEEMO_condition',qualified=True)
        self.assertEqual(self.system.page,'drive')
        self.assertIn('非本人心情实测',self.system.alerts['mood'])
        self.system.alerts.pop('mood')
        self.system.monitor('emotion','boring',self.now+1,source='GAMEEMO_condition',qualified=True)
        self.assertNotIn('mood',self.system.alerts)

    def test_unpresented_direction_and_clock_regression_cannot_act(self):
        self.system._enter('drive',self.now)
        self.assertFalse(self.system.arm_virtual_direction(self.now+2))
        self.now+=2;self.ready();self.system.arm_virtual_direction(self.now)
        self.system.ssvep(demo_snapshot(),self.now)
        self.assertFalse(self.system.choose(0,self.now-1))
        self.assertEqual(self.system.page,'drive');self.assertEqual(self.system.direction,'stop')
        self.assertFalse(self.system.mi(dict(),float('nan')))
        self.assertFalse(self.system.gaze(None,self.now))

    def test_fatigue_warning_latches_and_ack_never_restarts_motion(self):
        self.drive();self.system.arm_virtual_direction(self.now)
        self.system.ssvep(demo_snapshot(),self.now)
        self.system.monitor('fatigue','severe_candidate',self.now,source='model_candidate',qualified=True)
        self.assertEqual(self.system.direction,'stop');self.assertIn('fatigue',self.system.alerts)
        self.assertFalse(self.system.arm_virtual_direction(self.now))
        self.assertEqual(self.system.page,'fatigue_alert')
        self.assertFalse(self.system.acknowledge_alert('fatigue',self.now))
        self.system.monitor('fatigue',0,self.now+.1,source='live_model_candidate',qualified=True)
        self.assertIn('fatigue',self.system.alerts)
        self.assertTrue(self.system.acknowledge_alert('fatigue',self.now+.1))
        self.assertNotIn('fatigue',self.system.alerts)
        self.assertFalse(self.system.direction_armed)

    def test_only_negative_model_group_offers_music(self):
        for label in ('funny','calm','boring'):
            self.system.monitor('emotion',label,self.now,source='GAMEEMO_condition',qualified=True)
            self.assertNotIn('mood',self.system.alerts);self.assertEqual(self.system.page,'home')
        self.system.monitor('emotion','horror',self.now,source='GAMEEMO_condition',qualified=True)
        self.assertEqual(self.system.page,'music_offer')
        self.system.monitor('emotion','boring',self.now+.1,source='GAMEEMO_condition',qualified=True)
        self.assertEqual(self.system.page,'home');self.assertNotIn('mood',self.system.alerts)

    def test_fatigue_ack_rejects_unknown_mild_bad_quality_and_stale_normal(self):
        self.system.monitor('fatigue','severe_candidate',self.now,source='live_model_candidate',qualified=True)
        for label,quality in (('unknown',True),(1,True),(False,True),(0,False)):
            self.now+=.1
            self.system.monitor('fatigue',label,self.now,source='live_model_candidate',qualified=quality)
            self.assertFalse(self.system.acknowledge_alert('fatigue',self.now))
        self.system.monitor('fatigue',0,self.now+.1,source='live_model_candidate',qualified=True)
        self.assertFalse(self.system.acknowledge_alert('fatigue',self.now+2.2))
        self.assertIn('fatigue',self.system.alerts)
        self.system.signal_lost(self.now+2.3)
        self.assertFalse(self.system.acknowledge_alert('fatigue',self.now+2.3))

    def test_stale_or_lost_negative_result_does_not_keep_song_prompt(self):
        for method in ('tick','signal_lost'):
            system=SystemController(self.now)
            system.monitor('emotion','horror',self.now,source='GAMEEMO_condition',qualified=True)
            self.assertEqual(system.page,'music_offer')
            getattr(system,method)(self.now+2.1)
            self.assertEqual(system.page,'home');self.assertNotIn('mood',system.alerts)

    def test_hdmi_warning_entry_and_confirmation_returns_stopped_home(self):
        self.system.monitor('fatigue','severe_candidate',self.now,source='live_model_candidate',qualified=True)
        self.ready();self.choose(0)
        self.assertEqual(self.system.labels()[1],'查看疲劳警示')
        self.choose(1);self.assertEqual(self.system.page,'fatigue_alert')
        self.system.monitor('fatigue','normal',self.now,source='live_model_candidate',qualified=True)
        self.choose(1);self.assertEqual(self.system.page,'home');self.assertFalse(self.system.direction_armed)

    def test_idle_timeout_from_presentation_even_when_not_armed(self):
        self.system._enter('drive',self.now);self.now+=20
        self.system.tick(self.now);self.assertEqual(self.system.page,'drive')
        self.system.presented(self.system.page_id,self.now)
        self.system.tick(self.now+14.99);self.assertEqual(self.system.page,'drive')
        self.system.tick(self.now+15);self.assertEqual(self.system.page,'home')

    def test_only_new_trusted_windows_extend_idle_deadline_and_colour(self):
        self.drive();self.system.arm_virtual_direction(self.now)
        original=self.system.direction_idle_deadline
        self.system.ssvep(demo_snapshot(12),self.now)
        deadline=self.system.direction_idle_deadline
        self.assertGreater(deadline,original);self.assertEqual(self.system.selected_frequency,12)
        self.system.ssvep(demo_snapshot(12),self.now+.2)
        self.assertEqual(self.system.direction_idle_deadline,deadline)
        self.system.ssvep(demo_snapshot(12,end=1050),self.now+.3)
        self.assertGreater(self.system.direction_idle_deadline,deadline)
        self.system.ssvep(demo_snapshot(accepted=False),self.now+.4)
        self.assertIsNone(self.system.selected_frequency)
        self.system.tick(self.now+15.3);self.assertEqual(self.system.page,'home')

    def test_test_mode_disables_idle_exit_but_keeps_stop_and_signal_revocation(self):
        system=SystemController(self.now,direction_idle_enabled=False)
        system._enter('drive',self.now);system.presented(system.page_id,self.now)
        now=self.now+2
        self.assertTrue(system.arm_virtual_direction(now))
        self.assertTrue(system.direction_started(system.page_id,now))
        system.ssvep(demo_snapshot(12),now)
        self.assertIsNone(system.direction_idle_deadline)
        system.tick(now+16)
        self.assertEqual(system.page,'drive')
        self.assertEqual(system.direction,'stop')
        self.assertFalse(system.snapshot(now+16)['direction_idle_enabled'])
        system.signal_lost(now+17)
        self.assertEqual(system.direction,'stop');self.assertIsNone(system.selected_frequency)
        system.force_stop(now+18)
        self.assertEqual(system.page,'home');self.assertFalse(system.direction_armed)

    def test_force_stop_clears_old_evidence_and_requires_new_explicit_arm(self):
        self.drive();self.system.arm_virtual_direction(self.now)
        self.system.ssvep(demo_snapshot(14),self.now)
        self.assertTrue(self.system.force_stop(self.now+.01));self.now+=.01
        self.assertEqual(self.system.page,'home');self.assertTrue(self.system.force_stopped)
        self.system.ssvep(demo_snapshot(14,end=1050),self.now)
        self.assertEqual(self.system.direction,'stop');self.assertIsNone(self.system.selected_frequency)
        self.ready();self.drive();self.assertFalse(self.system.direction_armed)
        self.assertTrue(self.system.arm_virtual_direction(self.now));self.assertFalse(self.system.force_stopped)

    def test_corner_gaze_never_navigates_the_ssvep_screen(self):
        self.drive()
        for i in range(80):
            stamp=self.now+i*.025
            self.assertFalse(self.system.gaze(dict(valid=True,x=.1,monotonic_ns=int(stamp*1e9)),stamp))
        self.assertEqual(self.system.page,'drive')


if __name__=='__main__':unittest.main()
