import sys
import time
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.runtime import RuntimeCoordinator
from z20_compute.protocol import Message, CHANNELS
from z20_compute.video import FrameSnapshot


class EEGAdapter:
    def __init__(self): self.resets, self.samples = 0, 0
    def reset(self): self.resets += 1
    def feed(self, samples):
        self.samples += len(samples)
        return [dict(task="emotion", features=np.zeros(180), valid=True, state="ready", baseline={})]


class Classifier:
    def predict(self, values, **kwargs):
        return SimpleNamespace(class_id=1, scores=np.array([0., 4., 0.]), valid=True,
                               state="prediction", model_version="test-model", backend="test-adapter")


class RuntimeTests(unittest.TestCase):
    def test_delayed_network_pump_never_publishes_an_expired_valid_result(self):
        now = [10.]
        runtime = RuntimeCoordinator(models={"sound": Classifier()}, now=lambda:now[0])
        try:
            runtime.set_audio(True)
            runtime.submit_audio(1, 1000, .2*np.sin(2*np.pi*1000*np.arange(16000)/16000))
            self.assertTrue(runtime.audio.wait_for_sequence(1, 1))
            self.assertTrue(runtime.status()["sound"]["valid"])
            now[0] += 4
            result = next(m for m in runtime.poll() if m.body["task"] == "sound")
            self.assertFalse(result.body["valid"])
            self.assertIsNone(result.body["class_id"])
        finally:
            runtime.close()

    def test_audio_is_opt_in_silence_invalidates_and_disconnect_allows_new_sequence(self):
        eeg = EEGAdapter()
        runtime = RuntimeCoordinator(models={"sound": Classifier()}, eeg_adapter=eeg)
        tone = .2*np.sin(2*np.pi*1000*np.arange(16000)/16000)
        try:
            self.assertFalse(runtime.submit_audio(1, 10, tone))
            runtime.set_audio(True)
            runtime.submit_audio(1, 10, tone)
            self.assertTrue(runtime.audio.wait_for_sequence(1, 1))
            self.assertTrue(runtime.status()["sound"]["valid"])
            runtime.submit_audio(2, 20, np.zeros(16000))
            self.assertTrue(runtime.audio.wait_for_sequence(2, 1))
            self.assertFalse(runtime.status()["sound"]["valid"])
            for sequence in (10, 1):
                runtime.submit_eeg(Message("eeg", "cap", sequence, 1000,
                        dict(sample_rate_hz=250, channels=list(CHANNELS), samples=[[1.]*8])))
                deadline = time.monotonic()+1
                target = 1 if sequence == 10 else 2
                while eeg.samples < target and time.monotonic() < deadline: time.sleep(.001)
                if sequence == 10: runtime.disconnect_eeg()
            self.assertEqual(eeg.samples, 2)
            self.assertEqual(eeg.resets, 1)
        finally:
            runtime.close()

    def test_eeg_survives_frontend_switch_and_gap_resets_processing(self):
        eeg = EEGAdapter()
        runtime = RuntimeCoordinator(models={"emotion": Classifier()}, eeg_adapter=eeg)
        def send(sequence):
            runtime.submit_eeg(Message("eeg", "cap", sequence, 1000*sequence,
                    dict(sample_rate_hz=250, channels=list(CHANNELS), samples=[[1.]*8])))
            deadline = time.monotonic()+1
            while time.monotonic() < deadline and eeg.samples < (1 if sequence == 1 else 2 if sequence == 2 else 3):
                time.sleep(.001)
        try:
            send(1)
            runtime.set_mode("face")
            runtime.set_mode("stereo")
            send(2)
            self.assertEqual(eeg.resets, 0)
            self.assertEqual(eeg.samples, 2)
            send(4)
            self.assertEqual(eeg.resets, 1)
            results = runtime.poll()
            self.assertTrue(any(r.body["task"] == "emotion" and r.body["valid"] for r in results))
            runtime.disconnect_eeg()
            self.assertFalse(runtime.status()["emotion"]["valid"])
        finally:
            self.assertTrue(runtime.close())

    def test_slow_stereo_and_mode_changes_cannot_block_frame_submission(self):
        entered, release = threading.Event(), threading.Event()
        class Stereo:
            def process(self, left, right, **kwargs):
                entered.set()
                release.wait(1)
                return SimpleNamespace(distance_m=1.2, valid_mask=np.ones((240, 320), bool))
        runtime = RuntimeCoordinator(models={"face": Classifier()}, stereo=Stereo())
        pixels = np.tile(np.arange(320, dtype=np.uint8), (2, 240, 1))
        pixels.flags.writeable = False
        frame = FrameSnapshot(1, 1000, pixels)
        try:
            runtime.set_mode("stereo")
            runtime.submit_frame(frame, capture_mode="test")
            self.assertTrue(entered.wait(1))
            start = time.monotonic()
            for seq in range(2, 32): runtime.submit_frame(FrameSnapshot(seq, seq*1000, pixels), capture_mode="test")
            self.assertLess(time.monotonic()-start, .2)
            runtime.set_mode("face")
            release.set()
            runtime.submit_frame(FrameSnapshot(32, 32000, pixels), capture_mode="test", face_roi=(80, 60, 80, 80))
            deadline = time.monotonic()+1
            while time.monotonic() < deadline:
                runtime.poll()
                if runtime.status()["face"]["valid"]: break
                time.sleep(.001)
            self.assertTrue(runtime.status()["face"]["valid"])
            self.assertFalse(runtime.status()["stereo"]["valid"])
        finally:
            release.set()
            runtime.close()


if __name__ == "__main__": unittest.main()
