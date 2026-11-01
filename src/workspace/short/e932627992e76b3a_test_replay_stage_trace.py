import tempfile
import os
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from replay_stage_trace import StageTrace, install_primary


class TraceTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix', 'Worker requires Linux fork')
    def test_detailed_submission_trace_preserves_worker_payload_and_numpy(self):
        import contextlib
        import multiprocessing
        import numpy as np
        import async_primary
        import cyton_guardianloop as live
        from test_async_primary import BlockingProcessor, counters
        from replay_stage_trace import install_fast_path
        worker_class = async_primary.AsyncPrimaryWorker
        original_array = np.array
        context = multiprocessing.get_context('fork')
        started, release = context.Event(), context.Event()
        release.set()
        with contextlib.ExitStack() as restore:
            for owner, name in ((live.CausalEEGFilter, 'process'), (live.TelemetryWriter, 'submit'),
                    (live, 'publish_result'), (worker_class, 'poll'), (worker_class, 'submit'),
                    (worker_class, '__init__'), (async_primary, 'np')):
                restore.enter_context(patch.object(owner, name, getattr(owner, name)))
            trace = install_fast_path(live, detailed_submit=True)
            self.assertIs(np.array, original_array)
            worker = worker_class(BlockingProcessor(started, release))
            try:
                raw = np.ones((1, 8))
                self.assertTrue(worker.submit(raw, raw, [False], counters(1), time.monotonic()))
                raw[:] = 99
                replies = []
                deadline = time.monotonic()+2
                while not replies and time.monotonic() < deadline:
                    replies = worker.poll()
                    time.sleep(.005)
                self.assertEqual(replies[0]['result']['raw'], 1)
                self.assertEqual(trace.totals['primary_submit_array_copy']['calls'], 3)
                self.assertEqual(trace.totals['primary_submit_queue_put']['calls'], 1)
                self.assertGreater(trace.totals['primary_submit_generation_read']['calls'], 0)
                worker.invalidate()
                self.assertEqual(worker.generation[0], 1)
            finally:
                worker.close()
        self.assertIs(async_primary.np, np)

    def test_generation_proxy_preserves_shared_reads_writes_and_lock(self):
        import multiprocessing
        from replay_stage_trace import TracedGeneration
        original = multiprocessing.get_context('spawn').Array('q', [0, 0])
        trace = StageTrace()
        proxy = TracedGeneration(original, trace)
        self.assertIs(proxy.get_lock(), original.get_lock())
        with proxy.get_lock():
            proxy[0] += 1
            proxy[1] = 2
        self.assertEqual(proxy[:], [1, 2])
        self.assertEqual(original[:], [1, 2])
        self.assertEqual(trace.totals['primary_submit_generation_read']['calls'], 2)

    def test_redirected_log_preserves_text_and_return_value(self):
        import io
        from replay_stage_trace import TracedReplayLog
        stream, trace = io.StringIO(), StageTrace()
        wrapped = TracedReplayLog(stream, trace)
        self.assertEqual(wrapped.write('hello'), 5)
        wrapped.flush()
        self.assertEqual(stream.getvalue(), 'hello')
        self.assertEqual(trace.totals['primary_log_write']['calls'], 1)
        self.assertEqual(trace.totals['primary_log_flush']['calls'], 1)

    def test_nested_result_and_wait(self):
        class Work:
            def inner(self):
                time.sleep(.025)
                return 7
            def outer(self):
                return self.inner() + 1
        trace = StageTrace()
        trace.wrap(Work, 'inner', 'inner')
        trace.wrap(Work, 'outer', 'outer')
        self.assertEqual(Work().outer(), 8)
        self.assertEqual(trace.totals['inner']['calls'], 1)
        self.assertLess(trace.totals['outer']['exclusive_wall_s'], trace.totals['outer']['wall_s'])
        self.assertGreater(trace.totals['inner']['wall_s'], trace.totals['inner']['cpu_s'])
        self.assertFalse(trace.stack)

    def test_exception_preserved(self):
        class Work:
            def fail(self):
                raise ValueError('original')
        trace = StageTrace()
        trace.wrap(Work, 'fail', 'failure')
        with self.assertRaisesRegex(ValueError, 'original'):
            Work().fail()
        self.assertFalse(trace.stack)
        self.assertEqual(trace.totals['failure']['calls'], 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'trace.json'
            trace.save(path)
            self.assertIn('failure', path.read_text())

    def test_largest_call_keeps_paired_cpu_and_wall_even_after_event_cap(self):
        class Work:
            def run(self):
                return 'same'
        trace=StageTrace(slow_seconds=.05,max_slow_events=1)
        trace.wrap(Work,'run','work')
        with patch('replay_stage_trace.time.monotonic',side_effect=(1.,1.1,2.,2.7)), \
                patch('replay_stage_trace.time.thread_time',side_effect=(0.,.04,.1,.101)):
            self.assertEqual(Work().run(),'same')
            self.assertEqual(Work().run(),'same')
        self.assertEqual(len(trace.slow),1)
        self.assertEqual(trace.omitted,1)
        largest=trace.totals['work']['max_wall_call']
        self.assertAlmostEqual(largest['wall_ms'],700)
        self.assertAlmostEqual(largest['thread_cpu_ms'],1)
        self.assertAlmostEqual(largest['non_cpu_ms'],699)

    def test_no_serialization_during_wrapped_calls(self):
        class Work:
            def run(self):
                return 4
        trace=StageTrace(slow_seconds=0,max_slow_events=0)
        trace.wrap(Work,'run','work')
        with patch('replay_stage_trace.json.dumps',side_effect=AssertionError('hot-path serialization')):
            self.assertEqual(Work().run(),4)
        self.assertEqual(trace.omitted,1)
        self.assertFalse(trace.slow)

    def test_thread_resource_deltas_use_the_same_call(self):
        from types import SimpleNamespace
        trace=StageTrace(slow_seconds=0)
        trace.thread_usage=lambda: None
        class Work:
            def run(self):
                return 4
        trace.wrap(Work,'run','work')
        before=SimpleNamespace(ru_nvcsw=1,ru_nivcsw=2,ru_minflt=3,ru_majflt=4)
        after=SimpleNamespace(ru_nvcsw=4,ru_nivcsw=7,ru_minflt=10,ru_majflt=4)
        with patch.object(trace,'thread_usage',side_effect=(before,after)):
            self.assertEqual(Work().run(),4)
        self.assertEqual(trace.slow[0]['voluntary_switches'],3)
        self.assertEqual(trace.slow[0]['involuntary_switches'],5)
        self.assertEqual(trace.slow[0]['minor_faults'],7)
        self.assertEqual(trace.slow[0]['major_faults'],0)

    def test_primary_install_has_no_global_or_worker_hooks(self):
        from types import SimpleNamespace
        live=SimpleNamespace(**{name:object() for name in (
            'CausalEEGFilter','CytonSQIMonitor','CovarianceSVM','FourChannelFatigue','TelemetryWriter')})
        with patch('replay_stage_trace.StageTrace') as factory:
            trace=install_primary(live,object(),object())
        factory.assert_called_once_with(slow_seconds=.050,max_slow_events=256,thread_resources=True)
        labels=[call.args[2] for call in trace.wrap.call_args_list]
        self.assertEqual(len(labels),13)
        self.assertIn('primary_filter',labels)
        self.assertNotIn('array_stack',labels)
        self.assertNotIn('primary_log_write',labels)
        self.assertFalse(trace.wrap.call_args_list[-1].kwargs['resource_counts'])

    def test_per_packet_probe_can_omit_resource_reads(self):
        class Work:
            def run(self):
                return 'same'
        trace=StageTrace(slow_seconds=0)
        trace.thread_usage=lambda: None
        trace.wrap(Work,'run','work',resource_counts=False)
        with patch.object(trace,'thread_usage',side_effect=AssertionError('resource read')):
            self.assertEqual(Work().run(),'same')
        self.assertNotIn('involuntary_switches',trace.slow[0])


if __name__ == '__main__':
    unittest.main()
