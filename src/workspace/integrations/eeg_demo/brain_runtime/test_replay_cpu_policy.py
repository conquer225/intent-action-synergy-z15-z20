import sys
import unittest
from unittest.mock import patch


@unittest.skipUnless(sys.platform == 'linux', 'Private Linux scheduler harness')
class ReplayCPUPolicyTests(unittest.TestCase):
    def setUp(self):
        import soak_service_replay
        self.replay = soak_service_replay

    def test_cpu_profiles_keep_reference_and_split_distinct(self):
        self.assertEqual(self.replay.replay_cpu_roles(False, False),
            dict(parent=None, background=None, primary='0,1'))
        self.assertEqual(self.replay.replay_cpu_roles(True, False),
            dict(parent=0, background=1, primary='0,1'))
        self.assertEqual(self.replay.replay_cpu_roles(False, True),
            dict(parent=0, background=0, primary='inherit'))
        with self.assertRaises(ValueError):
            self.replay.replay_cpu_roles(True, True)

    def test_cpu0_background_workers_do_not_reopen_cpu1(self):
        import mi_acquisition
        import ssvep_acquisition
        for wrapper,module,target in (
                (self.replay.replay_mi_worker,mi_acquisition,'_mi_worker'),
                (self.replay.replay_ssvep_worker,ssvep_acquisition,'_worker')):
            with patch.object(self.replay.os, 'sched_setaffinity') as pin, \
                    patch.object(module, target, return_value='done'):
                self.assertEqual(wrapper('same-input', cpu=0), 'done')
                pin.assert_called_once_with(0, {0})

    def test_telemetry_worker_pins_before_dispatch_without_changing_payload(self):
        pending = object()
        with patch.object(self.replay.os, 'sched_setaffinity') as pin, \
                patch.object(self.replay, '_BASE_TELEMETRY_WORKER', return_value='done') as worker:
            self.assertEqual(self.replay.replay_telemetry_worker(pending, 1), 'done')
            pin.assert_called_once_with(0, {1})
            worker.assert_called_once_with(pending)

    def test_fork_inherited_wrapper_does_not_dispatch_back_to_itself(self):
        pending = object()
        with patch.object(self.replay.os, 'sched_setaffinity'), \
                patch.object(self.replay.live, '_telemetry_worker', self.replay.replay_telemetry_worker), \
                patch.object(self.replay, '_BASE_TELEMETRY_WORKER', return_value='done') as original:
            self.assertEqual(self.replay.replay_telemetry_worker(pending, 1), 'done')
            original.assert_called_once_with(pending)

    def test_real_fork_worker_exits_normally_with_inherited_wrapper(self):
        import functools
        import multiprocessing
        import os
        context = multiprocessing.get_context('fork')
        pending = context.Queue(maxsize=1)
        pending.put(None)
        target = functools.partial(self.replay.replay_telemetry_worker,
                                   cpu=max(os.sched_getaffinity(0)))
        process = context.Process(target=target, args=(pending,))
        try:
            with patch.object(self.replay.live, '_telemetry_worker', target):
                process.start()
                process.join(timeout=5)
            self.assertFalse(process.is_alive())
            self.assertEqual(process.exitcode, 0)
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
            pending.close()
            pending.join_thread()

    def test_mi_worker_pins_and_forwards_the_same_arguments(self):
        import mi_acquisition
        arguments = (object(), 'model', 'replay', '127.0.0.1', 0)
        with patch.object(self.replay.os, 'sched_setaffinity') as pin, \
                patch.object(mi_acquisition, '_mi_worker', return_value='done') as worker:
            self.assertEqual(self.replay.replay_mi_worker(*arguments, cpu=1), 'done')
            pin.assert_called_once_with(0, {1})
            worker.assert_called_once_with(*arguments)

    def test_ssvep_worker_has_no_implicit_affinity_in_the_reference(self):
        import ssvep_acquisition
        with patch.object(self.replay.os, 'sched_setaffinity') as pin, \
                patch.object(ssvep_acquisition, '_worker', return_value='done') as worker:
            self.assertEqual(self.replay.replay_ssvep_worker('same-input'), 'done')
            pin.assert_not_called()
            worker.assert_called_once_with('same-input')

    def test_process_stat_reports_actual_kernel_affinity(self):
        import os
        stats = self.replay.process_stats(os.getpid())
        self.assertEqual(stats['cpu_affinity'], sorted(os.sched_getaffinity(0)))
        self.assertEqual(stats['nice'], os.getpriority(os.PRIO_PROCESS,0))
        self.assertIsNone(self.replay.process_stats(2147483647))

    def test_default_policy_never_changes_priority(self):
        with patch.object(self.replay.os, 'setpriority') as priority:
            self.replay.configure_replay_worker(None)
            priority.assert_not_called()

    def test_worker_priority_is_absolute_and_set_before_dispatch(self):
        events=[]
        def dispatch(pending):
            events.append('dispatch')
        with patch.object(self.replay.os, 'sched_setaffinity'), \
                patch.object(self.replay.os, 'setpriority', side_effect=lambda *a: events.append(a)) as priority, \
                patch.object(self.replay, '_BASE_TELEMETRY_WORKER', side_effect=dispatch):
            self.replay.replay_telemetry_worker(None,1,nice=10)
            priority.assert_called_once_with(self.replay.os.PRIO_PROCESS,0,10)
        self.assertEqual(events,[(self.replay.os.PRIO_PROCESS,0,10),'dispatch'])

    def test_invalid_priority_does_not_change_any_scheduler_setting(self):
        with patch.object(self.replay.os, 'sched_setaffinity') as pin, \
                patch.object(self.replay.os, 'setpriority') as priority:
            for nice in (-10,1,20):
                with self.assertRaises(ValueError):
                    self.replay.configure_replay_worker(1,nice)
            pin.assert_not_called()
            priority.assert_not_called()

    def test_mi_and_ssvep_apply_the_requested_background_priority(self):
        import mi_acquisition
        import ssvep_acquisition
        for wrapper,module,target in (
                (self.replay.replay_mi_worker,mi_acquisition,'_mi_worker'),
                (self.replay.replay_ssvep_worker,ssvep_acquisition,'_worker')):
            with patch.object(self.replay.os,'sched_setaffinity'), \
                    patch.object(self.replay.os,'setpriority') as priority, \
                    patch.object(module,target,return_value='done'):
                self.assertEqual(wrapper('same-input',cpu=1,nice=10),'done')
                priority.assert_called_once_with(self.replay.os.PRIO_PROCESS,0,10)

    def test_real_fork_background_priority_leaves_parent_unchanged(self):
        import functools
        import multiprocessing
        import os
        context=multiprocessing.get_context('fork')
        receive,send=context.Pipe(duplex=False)
        before=self.replay.process_stats(os.getpid())
        target=functools.partial(self.replay.replay_telemetry_worker,
                                 cpu=max(os.sched_getaffinity(0)),nice=10)
        def report(connection):
            connection.send(self.replay.process_stats(os.getpid()))
        process=context.Process(target=target,args=(send,))
        try:
            with patch.object(self.replay.live,'_telemetry_worker',target), \
                    patch.object(self.replay,'_BASE_TELEMETRY_WORKER',report):
                process.start()
                self.assertTrue(receive.poll(5))
                actual=receive.recv()
                process.join(timeout=5)
            self.assertEqual(process.exitcode,0)
            self.assertEqual(actual['nice'],10)
            self.assertEqual(actual['cpu_affinity'],[max(before['cpu_affinity'])])
            after=self.replay.process_stats(os.getpid())
            self.assertEqual(after['nice'],before['nice'])
            self.assertEqual(after['cpu_affinity'],before['cpu_affinity'])
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
            receive.close()
            send.close()


if __name__ == '__main__':
    unittest.main()
