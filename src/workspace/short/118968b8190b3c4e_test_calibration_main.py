"""Full ARM-loop fault injection; generated input is not an accuracy test."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from test_primary_stream_recovery import FATIGUE_MODEL
from calibration_session import CalibrationSession
from wear_session import WearSession
from cyton_fatigue import FourChannelFatigue
from cyton_sqi import CausalEEGFilter, CytonSQIMonitor


def generated_signal(count, seed):
    t = np.arange(count) / 250
    return np.stack([20*np.sin(2*np.pi*(8+i)*t) for i in range(8)], axis=1) + np.random.default_rng(seed).normal(0, 1, (count,8))


@unittest.skipUnless(os.name == 'posix', 'ARM main loop requires Linux')
class CalibrationMainTests(unittest.TestCase):
    def run_main(self, directory, count, faults=False, new_wear=False, covariance_model=None,
                 async_primary=False, reconnect=False):
        import cyton_guardianloop as live

        clock = [100.]
        values = generated_signal(count, 87)
        counts = np.rint(values / live.DEFAULT_UV_PER_COUNT).astype(int)
        reports = []
        cursor = [0]
        configuration_count = [0]

        def configure(fd):
            configuration_count[0] += 1

        def frames(*args, **kwargs):
            while cursor[0] < count:
                index = cursor[0]
                if reconnect and index == 1000 and configuration_count[0] == 1:
                    clock[0] += 5.1
                    kwargs['on_idle'](clock[0])
                    self.fail('Long silence must reopen the reader')
                row = counts[index]
                cursor[0] += 1
                clock[0] = 100. + index / 250 + (5.1 if reconnect and configuration_count[0] > 1 else 0.)
                if new_wear and index==2000:
                    control=WearSession(directory,lambda:clock[0])
                    control.request_new(control.snapshot()['id'])
                if faults and index == 3200:
                    clock[0] += 1
                    kwargs['on_idle'](clock[0])
                body = b''.join((int(v) & 0xFFFFFF).to_bytes(3, 'big') for v in row)
                frame = bytes((0xA0, index % 256)) + body + bytes(6) + bytes((0xC0,))
                malformed = 1 if faults and 3400 <= index < 3500 else 0
                age = 2. if faults and 4200 <= index < 5200 else 0.
                yield frame, malformed, clock[0] - age

        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(patch.dict(os.environ, {'GL_SEED_EXECUTION':'sync'}))
            for name in ('configure_serial', 'write_command'):
                stack.enter_context(patch.object(live, name))
            stack.enter_context(patch.object(live, 'configure_eeg_channels', side_effect=configure))
            stack.enter_context(patch.object(live.termios, 'tcflush'))
            stack.enter_context(patch.object(live.signal, 'signal'))
            stack.enter_context(patch.object(live.time, 'sleep'))
            stack.enter_context(patch.object(live.time, 'monotonic', side_effect=lambda:clock[0]))
            stack.enter_context(patch.object(live, 'WearSession',side_effect=lambda path:WearSession(path,lambda:clock[0])))
            stack.enter_context(patch.object(live, 'packets', side_effect=frames))
            stack.enter_context(patch.object(live, 'SeedShadow', return_value=None))
            stack.enter_context(patch.object(live, 'SSVEPReaderRuntime', return_value=None))
            stack.enter_context(patch.object(live, 'TelemetryWriter'))
            recorder = stack.enter_context(patch.object(live, 'TrialRecorder')).return_value
            recorder.active = None
            original = live.publish_result

            def publish(row, *args, **kwargs):
                reports.append(json.loads(json.dumps(row)))
                return original(row, *args, **kwargs)

            stack.enter_context(patch.object(live, 'publish_result', side_effect=publish))
            stack.enter_context(patch.object(sys, 'argv', [
                'isolated-main-test', '--port', '/dev/null', '--esp32-url', '',
                *(['--isolated-primary-worker'] if async_primary else ['--wait-for-data']),
                '--fatigue-model', str(FATIGUE_MODEL),
                '--covariance-model', str(covariance_model or Path(directory)/'no-emotion-model'),
                '--emotion-model', str(Path(directory)/'no-legacy-model'),
                '--status-file', str(Path(directory)/'status.json'),
                '--telemetry-file', str(Path(directory)/'telemetry.json')]))
            live.main()
            self.assertEqual(recorder.append.call_count, count)
            self.assertEqual(configuration_count[0], 2 if reconnect else 1)
        return reports

    def test_complete_calibration_survives_faults_and_main_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            import cyton_guardianloop as live
            sqi, fatigue = CytonSQIMonitor(), FourChannelFatigue(FATIGUE_MODEL)
            filtered = CausalEEGFilter().process(generated_signal(16*2000, 86))
            for clean in filtered.reshape(16,2000,8):
                sqi.process(clean);fatigue.append(clean);fatigue.process_window(True, True)
            context = CalibrationSession.context_for('/dev/null', live.DEFAULT_CHANNEL_MAP,
                live.DEFAULT_UV_PER_COUNT, (FATIGUE_MODEL,), 'arm')
            context['wear_id'] = WearSession(directory).initialize()
            CalibrationSession(Path(directory)/'calibration-session.json', context).save(sqi,fatigue)
            reports = self.run_main(directory, 10000, faults=True)
            faults = [r for r in reports if r.get('reason') in
                      ('STREAM_IDLE', 'MALFORMED_STREAM', 'PROCESSING_BACKLOG')]
            self.assertTrue(faults)
            self.assertTrue(any(r.get('reason') == 'PROCESSING_BACKLOG' for r in faults))
            self.assertTrue(all(not r['valid'] and not r['emotion']['valid'] for r in faults))
            self.assertTrue(all(r['calibration_current'] == 15 for r in faults))
            self.assertTrue(all(r['calibration_retained'] for r in faults))
            last_fault = max(i for i, r in enumerate(reports) if r in faults)
            resumed = [r for r in reports[last_fault+1:] if r.get('state') in ('NORMAL','MILD','SEVERE')]
            self.assertTrue(resumed, [(r.get('state'),r.get('reason'),
                r.get('sqi',{}).get('overall_quality')) for r in reports])
            self.assertTrue(all(r['calibration_current'] == 15 for r in resumed))
            checkpoint = json.loads((Path(directory)/'calibration-session.json').read_text())
            self.assertEqual(len(checkpoint['fatigue']['baseline']), 15)
            self.assertTrue(all(checkpoint['sqi']['calibrated_channels']))
            restarted = self.run_main(directory, 4000)
            self.assertEqual(restarted[0]['reason'], 'STREAM_STARTING')
            self.assertFalse(restarted[0]['valid'])
            self.assertEqual(restarted[0]['calibration_current'], 15)
            self.assertTrue(any(r.get('state') in ('NORMAL','MILD','SEVERE') for r in restarted))
            self.assertFalse(any(r.get('state') == 'CALIBRATING' for r in restarted))
            calibration_before = (Path(directory)/'calibration-session.json').read_bytes()
            reconnected = self.run_main(directory, 5000, reconnect=True)
            starting = [r for r in reconnected if r.get('reason') == 'STREAM_STARTING']
            self.assertEqual(len(starting), 2)
            self.assertTrue(all(r['calibration_current'] == 15 and not r['valid'] for r in starting))
            self.assertTrue(any(r.get('reason') == 'STREAM_IDLE' for r in reconnected))
            self.assertFalse(any(r.get('state') == 'CALIBRATING' for r in reconnected))
            self.assertTrue(any(r.get('state') in ('NORMAL','MILD','SEVERE') for r in reconnected))
            self.assertEqual((Path(directory)/'calibration-session.json').read_bytes(), calibration_before)
            old_wear=WearSession(directory).snapshot()['id']
            changed=self.run_main(directory,4000,new_wear=True)
            reset=[r for r in changed if r.get('reason')=='EXPLICIT_NEW_WEARING']
            self.assertTrue(reset);self.assertEqual(reset[0]['calibration_current'],0)
            self.assertFalse(reset[0]['valid']);self.assertFalse(reset[0]['calibration_retained'])
            self.assertNotEqual(WearSession(directory).snapshot()['id'],old_wear)


if __name__ == '__main__':
    unittest.main()
