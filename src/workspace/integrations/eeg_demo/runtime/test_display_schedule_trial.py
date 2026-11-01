"""Scheduler guard checks without touching a real process, USB or PL."""
import unittest
from unittest.mock import patch

import display_schedule_trial as trial


def state(nice=5, start=123):
    return dict(start_ticks=start, nice=nice, policy=0, affinity=[0, 1])


class DisplayScheduleTests(unittest.TestCase):
    def setUp(self):
        self.plan = dict(pid=900, session='play-df4fc516', original_nice=5)

    def test_sets_and_verifies_each_ordinary_thread(self):
        values = {900: state(), 947: state(start=124)}
        def change(which, tid, nice):
            values[tid] = dict(values[tid], nice=nice)
        with patch.object(trial, 'current_threads', side_effect=lambda p: dict(values)), \
                patch.object(trial, 'thread_state', side_effect=lambda p, t: values[t]), \
                patch.object(trial.os, 'PRIO_PROCESS', 0, create=True), \
                patch.object(trial.os, 'setpriority', side_effect=change, create=True) as setter:
            result = trial.set_display_nice(self.plan, 0)
        self.assertEqual(setter.call_count, 2)
        self.assertTrue(all(v['nice'] == 0 for v in result.values()))

    def test_restore_includes_cache_reader_created_during_trial(self):
        values = {900: state(0), 1400: state(0, 300)}
        def change(which, tid, nice):
            values[tid] = dict(values[tid], nice=nice)
        with patch.object(trial, 'current_threads', side_effect=lambda p: dict(values)), \
                patch.object(trial, 'thread_state', side_effect=lambda p, t: values[t]), \
                patch.object(trial.os, 'PRIO_PROCESS', 0, create=True), \
                patch.object(trial.os, 'setpriority', side_effect=change, create=True):
            trial.set_display_nice(self.plan, 5)
            trial.set_display_nice(self.plan, 5)
        self.assertTrue(all(v['nice'] == 5 for v in values.values()))

    def test_unexpected_rt_priority_or_affinity_is_not_modified(self):
        for changed in (dict(policy=2), dict(nice=-1), dict(affinity=[1])):
            with self.subTest(changed=changed), \
                    patch.object(trial, 'current_threads', return_value={900: dict(state(), **changed)}), \
                    patch.object(trial.os, 'setpriority', create=True) as setter:
                with self.assertRaisesRegex(RuntimeError, 'Unexpected scheduler'):
                    trial.set_display_nice(self.plan, 0)
                setter.assert_not_called()

    def test_reused_thread_is_not_modified(self):
        with patch.object(trial, 'current_threads', return_value={900: state()}), \
                patch.object(trial, 'thread_state', return_value=state(start=999)), \
                patch.object(trial.os, 'setpriority', create=True) as setter:
            with self.assertRaisesRegex(RuntimeError, 'Thread changed'):
                trial.set_display_nice(self.plan, 0)
            setter.assert_not_called()

    def test_changed_boot_is_rejected_before_reading_threads(self):
        with patch.object(trial.BOOT.__class__, 'read_text', return_value='new-boot'), \
                patch.object(trial, 'thread_state') as reader:
            with self.assertRaisesRegex(RuntimeError, 'boot changed'):
                trial.current_threads(dict(self.plan, boot='old-boot'))
            reader.assert_not_called()

    def test_reused_display_pid_is_rejected(self):
        with patch.object(trial.BOOT.__class__, 'read_text', return_value='boot'), \
                patch.object(trial, 'thread_state', return_value=state(start=999)):
            with self.assertRaisesRegex(RuntimeError, 'PID was reused'):
                trial.current_threads(dict(self.plan, boot='boot', start_ticks=123))

    def test_scope_change_ends_trial_without_display_commands(self):
        row = dict(session='play-df4fc516', page='video', state='playing',
            physical=False, stimulus=False, silent=True, direction='stop')
        for changed in (dict(page='home'), dict(stimulus=True), dict(physical=True),
                        dict(session='another'), dict(silent=False), dict(direction='left')):
            with self.subTest(changed=changed), \
                    patch.object(trial, 'current_threads', return_value={900: state()}), \
                    patch.object(trial, 'sample_display', return_value=dict(row, **changed)):
                with self.assertRaisesRegex(RuntimeError, 'display scope'):
                    trial.safe_sample(self.plan, 5)

    def test_restore_reports_failure_instead_of_success(self):
        with patch.object(trial, 'set_display_nice', side_effect=RuntimeError('failed')), \
                patch.object(trial, 'write_json') as writer:
            from pathlib import Path
            with self.assertRaises(RuntimeError):
                trial.restore(Path('/private'), self.plan)
            self.assertFalse(writer.call_args.args[1]['restored'])

    def test_cpu_division_sets_all_threads_without_changing_nice(self):
        values = {900: state(), 947: state(start=124)}
        def change(tid, affinity):
            values[tid] = dict(values[tid], affinity=sorted(affinity))
        with patch.object(trial, 'current_threads', side_effect=lambda p: dict(values)), \
                patch.object(trial, 'thread_state', side_effect=lambda p, t: values[t]), \
                patch.object(trial.os, 'sched_setaffinity', side_effect=change, create=True) as setter:
            result = trial.set_display_affinity(dict(self.plan, original_affinity=[0, 1]), [1])
        self.assertEqual(setter.call_count, 2)
        self.assertTrue(all(v['nice'] == 5 and v['affinity'] == [1] for v in result.values()))

    def test_cpu_restore_includes_new_cache_thread_and_is_idempotent(self):
        values = {900: dict(state(), affinity=[1]), 1400: dict(state(start=300), affinity=[1])}
        def change(tid, affinity):
            values[tid] = dict(values[tid], affinity=sorted(affinity))
        plan = dict(self.plan, kind='cpu-division', original_affinity=[0, 1])
        with patch.object(trial, 'current_threads', side_effect=lambda p: dict(values)), \
                patch.object(trial, 'thread_state', side_effect=lambda p, t: values[t]), \
                patch.object(trial.os, 'sched_setaffinity', side_effect=change, create=True), \
                patch.object(trial, 'write_json') as writer:
            from pathlib import Path
            trial.restore(Path('/private'), plan)
            trial.restore(Path('/private'), plan)
        self.assertTrue(writer.call_args.args[1]['restored'])
        self.assertTrue(all(v['affinity'] == [0, 1] for v in values.values()))

    def test_cpu_division_rejects_foreign_scheduler_state_and_reused_thread(self):
        plan = dict(self.plan, original_affinity=[0, 1])
        for changed in (dict(policy=2), dict(nice=0), dict(affinity=[0])):
            with self.subTest(changed=changed), \
                    patch.object(trial, 'current_threads', return_value={900: dict(state(), **changed)}), \
                    patch.object(trial.os, 'sched_setaffinity', create=True) as setter:
                with self.assertRaisesRegex(RuntimeError, 'Unexpected scheduler'):
                    trial.set_display_affinity(plan, [1])
                setter.assert_not_called()
        with patch.object(trial, 'current_threads', return_value={900: state()}), \
                patch.object(trial, 'thread_state', return_value=state(start=999)), \
                patch.object(trial.os, 'sched_setaffinity', create=True) as setter:
            with self.assertRaisesRegex(RuntimeError, 'Thread changed'):
                trial.set_display_affinity(plan, [1])
            setter.assert_not_called()

    def test_cpu_sample_requires_every_thread_on_the_expected_cpu(self):
        row = dict(session='play-df4fc516', page='video', state='playing',
            physical=False, stimulus=False, silent=True, direction='stop')
        threads = {900: dict(state(), affinity=[1])}
        with patch.object(trial, 'current_threads', return_value=threads), \
                patch.object(trial, 'sample_display', return_value=row):
            result = trial.safe_sample(self.plan, 5, [1])
            self.assertEqual(result['thread_affinity'], {'900': [1]})
            with self.assertRaisesRegex(RuntimeError, 'scheduling changed'):
                trial.safe_sample(self.plan, 5, [0, 1])

    def test_failed_affinity_verification_is_not_reported_as_success(self):
        with patch.object(trial, 'current_threads', return_value={900: state()}), \
                patch.object(trial, 'thread_state', return_value=state()), \
                patch.object(trial.os, 'sched_setaffinity', create=True):
            with self.assertRaisesRegex(RuntimeError, 'not verified'):
                trial.set_display_affinity(dict(self.plan, original_affinity=[0, 1]), [1])


if __name__ == '__main__':
    unittest.main()
