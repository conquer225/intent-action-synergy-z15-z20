"""The added EEG observer never owns acquisition or actuator decisions."""
from pathlib import Path
import json
import queue
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/workspace/integrations'))
from pl_accel.live import EEGComparison, LiveEEGTap
from pl_accel.eeg import EEGReference, EEGModel
from test_pl_eeg import identity_model


class EEGComparisonContract(unittest.TestCase):
    def test_new_windows_and_sequence_gap_withdrawal(self):
        observer = EEGComparison(EEGReference(identity_model()), microvolts_per_count=1., now=lambda: 10.)
        for i in range(4):
            x = np.zeros(8, np.int32);x[2] = (-1)**i;x[3] = 2*(-1)**i
            observer.ingest(x, i, received_at=9.9+i*.004)
        self.assertTrue(observer.snapshot()['valid'])
        self.assertEqual(observer.snapshot()['label'], 'right')
        self.assertFalse(observer.snapshot()['control_enabled'])
        observer.ingest(np.ones(8, np.int32), 7, received_at=9.93)
        self.assertFalse(observer.snapshot()['valid'])
        self.assertIsNone(observer.snapshot()['label'])

    def test_stale_input_is_rejected_before_inference(self):
        observer = EEGComparison(EEGReference(identity_model()), now=lambda: 10.)
        observer.ingest(np.ones(8, np.int32), 1, received_at=1.)
        self.assertFalse(observer.snapshot()['valid'])
        self.assertEqual(observer.snapshot()['reason'], 'stale_input')

    def test_saturation_withdraws_then_rebuilds_a_clean_window(self):
        base = identity_model()
        model = EEGModel(base.sos, base.csp*2, base.svm, base.bias, window=4, hop=2)
        observer = EEGComparison(EEGReference(model), now=lambda: 10.)
        for i in range(4):
            x=np.zeros(8,np.int32);x[2:4]=[(-1)**i*32767,(-1)**i*32767]
            observer.ingest(x,i,received_at=9.9+i*.004)
        self.assertEqual(observer.snapshot()['reason'], 'signal_clipping')
        for i in range(4,8):
            x=np.zeros(8,np.int32);x[2:4]=[(-1)**i,2*(-1)**i]
            observer.ingest(x,i,received_at=9.9+i*.004)
        self.assertTrue(observer.snapshot()['valid'])
        self.assertEqual(observer.snapshot()['sample_count'], 4)

    def test_stream_reset_restarts_window_without_blocking_acquisition(self):
        published = queue.Queue()
        sink = SimpleNamespace(pending=queue.Queue(), close=lambda: None)
        observer = EEGComparison(EEGReference(identity_model()), publish=published.put)
        tap = LiveEEGTap(observer, sink, lambda packet: np.array(packet[2:], np.int32))
        ordinal = 0
        def send(count):
            nonlocal ordinal
            for _ in range(count):
                ordinal += 1
                x = [0]*8;x[2] = (-1)**ordinal;x[3] = 2*(-1)**ordinal
                sink.pending.put((ordinal, [0, ordinal % 256]+x, False, time.monotonic()))
        try:
            send(4)
            self.assertTrue(published.get(timeout=2)['valid'])
            tap.interrupt('stream_reconfigured')
            reset = published.get(timeout=2)
            self.assertFalse(reset['valid'])
            self.assertEqual(reset['reason'], 'stream_reconfigured')
            send(4)
            result = published.get(timeout=2)
            self.assertEqual(result['sample_count'], 4)
            self.assertFalse(result['control_enabled'])
        finally:
            tap.close()

    def test_optional_hardware_start_failure_publishes_status_and_returns(self):
        runtime = Path(__file__).resolve().parents[1]/'src/workspace/integrations/eeg_demo/brain_runtime'
        sys.path.insert(0, str(runtime))
        from pl_mi import create_pl_mi
        from pl_accel.eeg import CHANNELS
        with tempfile.TemporaryDirectory() as directory:
            model_path, status_path = Path(directory)/'model.json', Path(directory)/'status.json'
            identity_model().save(model_path)
            def unavailable(*_):raise ValueError('missing integrated IP')
            observer = create_pl_mi(model_path, CHANNELS, status_path=status_path,
                packet_decoder=lambda p: p, engine_factory=unavailable)
            self.assertIsNone(observer)
            state = json.loads(status_path.read_text(encoding='utf-8'))
            self.assertFalse(state['valid'])
            self.assertEqual(state['reason'], 'backend_unavailable')
            self.assertFalse(state['control_enabled'])


if __name__ == '__main__':unittest.main()
