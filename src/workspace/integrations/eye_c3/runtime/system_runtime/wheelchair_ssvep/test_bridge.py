import copy
import unittest

from dry_run_bridge import DirectionPreview, demo_snapshot, validate_source_url


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.preview = DirectionPreview()

    def stop(self, s):
        result = self.preview.observe(s, 1)
        self.assertEqual(result['preview_direction'], 'stop')
        self.assertIs(result['motor_command_sent'], False)
        return result

    def test_four_directions_are_preview_only(self):
        for hz, direction in ((8, 'forward'), (10, 'backward'), (12, 'left'), (14, 'right')):
            with self.subTest(hz=hz):
                result = DirectionPreview().observe(demo_snapshot(hz), 1)
                self.assertEqual(result['preview_direction'], direction)
                self.assertEqual(result['legacy_method_reference'], 'POST')
                self.assertEqual(result['legacy_interface_evidence'], 'provided_backup_not_running_firmware')
                self.assertFalse(result['physical_output_enabled'])
                self.assertFalse(result['motor_command_sent'])

    def test_cleared_selection_and_stop(self):
        self.stop(demo_snapshot(accepted=False))
        self.stop(demo_snapshot(state='stopped'))

    def test_missing_and_non_object(self):
        for data in (None, [], 'broken', {}, 3):
            self.stop(data)

    def test_nonlive_and_changed_producer(self):
        for changes in ({'source': 'replay'}, {'state_owner': 'web'},
                        {'control_enabled': True}, {'production_eligible': True},
                        {'policy': 'future-policy'}):
            self.stop(demo_snapshot(**changes))

    def test_display_hidden_or_bad_frames(self):
        self.stop(demo_snapshot(frame_ok=False))

    def test_hdmi_policy_requires_native_timing_evidence(self):
        native=demo_snapshot(policy='ssvep-hdmi-experimental-v1',display_backend='hdmi_scan',
            display_page_id=7,display_timing=dict(schema='guardianloop-hdmi-latch-v1',
                source='hardware_latch_reports',ready=True,error=None))
        self.assertEqual(DirectionPreview().observe(native,1)['preview_direction'],'forward')
        for changed in ({'ready':False},{'source':'browser'},{'error':'skipped scan'}):
            invalid=copy.deepcopy(native);invalid['display_timing'].update(changed)
            self.stop(invalid)
        self.stop(demo_snapshot(policy='ssvep-hdmi-experimental-v1'))

    def test_warmup_or_bad_quality(self):
        for inp in ({'ready': False}, {'ready': True, 'quality': {}},
                    {'ready': True, 'quality': {'hard_bad': True}, 'age_seconds': .01}):
            self.stop(demo_snapshot(input=inp))

    def test_stale_nan_bool_and_negative_age(self):
        for age in (.51, float('nan'), True, -.01, None):
            s = demo_snapshot()
            s['input']['age_seconds'] = age
            self.stop(s)

    def test_request_latency_is_part_of_age(self):
        result = self.preview.observe(demo_snapshot(), 1, request_seconds=.49)
        self.assertEqual(result['preview_direction'], 'stop')

    def test_malformed_decision(self):
        for field, value in (('score', float('nan')), ('margin', .09), ('top_hz', 12),
                             ('failures', ['weak']), ('window_end_index_exclusive', True)):
            s = demo_snapshot()
            s['decision'][field] = value
            self.stop(s)

    def test_unconfirmed_and_unknown_frequency(self):
        self.stop(demo_snapshot(evidence_windows=1))
        self.stop(demo_snapshot(9))
        self.stop(demo_snapshot(8, frequencies=[10, 12]))

    def test_repeated_poll_cannot_keep_old_result(self):
        s = demo_snapshot()
        self.assertEqual(self.preview.observe(s, 1)['preview_direction'], 'forward')
        self.assertEqual(self.preview.observe(s, 1.46)['preview_direction'], 'stop')

    def test_window_gap_and_regression_stop(self):
        for end in (900, 1200):
            p = DirectionPreview()
            p.observe(demo_snapshot(), 1)
            self.assertEqual(p.observe(demo_snapshot(end=end), 1.2)['preview_direction'], 'stop')

    def test_new_session_can_restart_preview(self):
        self.preview.observe(demo_snapshot(), 1)
        s = demo_snapshot(12, 500, id='another-session')
        self.assertEqual(self.preview.observe(s, 1.2)['preview_direction'], 'left')

    def test_clock_regression_stop(self):
        self.preview.observe(demo_snapshot(), 2)
        self.stop(demo_snapshot())

    def test_does_not_change_classifier_payload(self):
        s = demo_snapshot()
        original = copy.deepcopy(s)
        self.preview.observe(s, 1)
        self.assertEqual(s, original)

    def test_only_exact_read_only_url_allowed(self):
        good = 'http://192.168.2.99:9102/api/ssvep-free'
        self.assertEqual(validate_source_url(good), good)
        for url in ('http://192.168.4.1/start', 'http://192.168.4.1:80/stop',
                    good + '?action=start', 'http://user:pass@192.168.2.99:9102/api/ssvep-free',
                    'http://8.8.8.8:80/api/ssvep-free', 'http://example.com:80/api/ssvep-free'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_source_url(url)


if __name__ == '__main__':
    unittest.main()
