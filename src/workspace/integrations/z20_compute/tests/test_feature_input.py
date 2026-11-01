import dataclasses
import json
import socket
import struct
import time
import unittest
from types import SimpleNamespace

import numpy as np

from z20_compute.protocol import Decoder, Message, encode


def feature(task="fatigue", window="recording-1:8", **changes):
    body = dict(task=task, feature_version="fatigue-calibrated-de20-v1",
                vector=[1.] * 20, window_id=window, source="recorded:lemon",
                valid=True, quality=1., reason="ok")
    body.update(changes)
    return Message("features", "client-a", 1, 0, body)


class FeatureProtocolTests(unittest.TestCase):
    def test_upstream_original_reference_has_explicit_label_and_score_contract(self):
        ref=dict(kind='HGB_regressor',class_id=1,value=.42)
        record=feature(original_reference=ref)
        self.assertEqual(Decoder().feed(encode(record)),[record])
        for bad in [dict(ref,class_id=3),dict(ref,value=float('inf')),dict(ref,kind='unknown')]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):encode(feature(original_reference=bad))

    def test_software_key_events_are_versioned_and_bounded_to_navigation(self):
        key=Message('command','client-a',1,0,dict(op='key_event',event='key1_long'))
        wire=encode(key)
        self.assertEqual(json.loads(wire[4:])['version'],2)
        self.assertEqual(Decoder().feed(wire),[key])
        with self.assertRaises(ValueError):encode(dataclasses.replace(key,body=dict(op='key_event',event='shutdown')))

    def test_feature_records_use_v2_and_legacy_ping_stays_v1(self):
        message = feature()
        wire = encode(message)
        self.assertEqual(json.loads(wire[4:])["version"], 2)
        self.assertEqual(Decoder().feed(wire[:9]) + Decoder().feed(b""), [])
        self.assertEqual(Decoder().feed(wire), [message])
        old = Message("ping", "old", 0, 0, {})
        self.assertEqual(json.loads(encode(old)[4:])["version"], 1)
        downgraded = json.loads(wire[4:]); downgraded["version"] = 1
        payload = json.dumps(downgraded).encode()
        with self.assertRaises(ValueError):
            Decoder().feed(struct.pack("!I", len(payload)) + payload)

    def test_bad_features_rejected_and_invalid_input_cannot_keep_vector(self):
        cases = [dict(vector=[1.] * 19), dict(vector=[float("inf")] * 20),
                 dict(vector=[True] * 20), dict(quality=-.1), dict(valid=1),
                 dict(window_id=""), dict(source=""), dict(feature_version=""),
                 dict(task="face"), dict(valid=False), dict(reason="")]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                encode(feature(**change))
        self.assertEqual(Decoder().feed(encode(feature(valid=False, vector=None, reason="bad_signal"))),
                         [feature(valid=False, vector=None, reason="bad_signal")])


class FeatureRuntimeTests(unittest.TestCase):
    def test_delayed_network_pump_cannot_publish_a_previously_queued_valid_result(self):
        from z20_compute.feature_runtime import FeatureRuntime
        class Classifier:
            version='delayed-pump-v1'
            def predict(self,values,*,backend):
                return SimpleNamespace(valid=True,class_id=2,scores=np.array([0.,1.,2.]),
                    state='prediction',model_version=self.version,backend='PS')
        clock=[10.]
        runtime=FeatureRuntime({'fatigue':Classifier()},now=lambda:clock[0])
        try:
            runtime.submit_features(feature())
            deadline=time.monotonic()+1
            while not runtime.status()['fatigue']['valid'] and time.monotonic()<deadline:time.sleep(.005)
            clock[0]=31.
            messages=runtime.poll()
            self.assertTrue(messages)
            self.assertFalse(any(message.body['valid'] for message in messages))
            self.assertEqual(messages[-1].body['state'],'expired')
        finally:runtime.close()

    def test_navigation_keeps_existing_eeg_window_and_source_session(self):
        from z20_compute.feature_runtime import FeatureRuntime
        from z20_compute.headless_keys import Navigation
        nav=Navigation();runtime=FeatureRuntime({},navigation=nav)
        try:
            runtime.submit_features(feature())
            deadline=time.monotonic()+1
            while not runtime.status()['fatigue'].get('window_id') and time.monotonic()<deadline:time.sleep(.005)
            before=runtime.status()['fatigue']
            for _ in range(12):runtime.apply_key('key1_short')
            runtime.apply_key('key1_long')
            self.assertEqual(nav.page,'overview')
            self.assertEqual(runtime.status()['fatigue']['window_id'],before['window_id'])
            self.assertEqual(runtime.remote_session,'client-a')
            self.assertFalse(runtime.submit_features(feature()))
        finally:runtime.close()

    def test_expiry_clears_both_ps_and_pl_and_disconnect_keeps_its_reason(self):
        from z20_compute.feature_runtime import FeatureRuntime
        class Classifier:
            version = 'comparison-v1'
            def predict(self, values, *, backend):
                return SimpleNamespace(valid=True, class_id=2, scores=np.array([0., 1., 2.]),
                    state='prediction', model_version=self.version, backend='PL' if backend else 'PS')
        clock = [10.]
        runtime = FeatureRuntime({'fatigue': Classifier()}, backend=object(), now=lambda: clock[0])
        try:
            runtime.submit_features(feature())
            deadline = time.monotonic()+1
            while not runtime.status()['fatigue']['valid'] and time.monotonic() < deadline: time.sleep(.005)
            clock[0] = 31.
            body = runtime.status()['fatigue']
            self.assertFalse(body['valid']); self.assertIsNone(body['ps_class_id'])
            self.assertIsNone(body['ps_scores'])
            runtime.disconnect_eeg(); clock[0] += 100
            self.assertEqual(runtime.status()['fatigue']['state'], 'disconnected')
        finally: runtime.close()

    def test_pl_disagreement_is_invalid_and_keeps_comparison_evidence(self):
        from z20_compute.feature_runtime import FeatureRuntime
        class Classifier:
            version = 'check-v1'
            def predict(self, values, *, backend):
                return SimpleNamespace(valid=True, class_id=0 if backend is None else 1,
                    scores=np.array([1., 0., 0.]) if backend is None else np.array([0., 1., 0.]),
                    state='prediction', model_version=self.version, backend='PS' if backend is None else 'PL')
        runtime = FeatureRuntime({'fatigue': Classifier()}, backend=object())
        try:
            runtime.submit_features(feature())
            deadline = time.monotonic()+1
            while runtime.status()['fatigue']['state'] == 'waiting_input' and time.monotonic() < deadline:
                time.sleep(.005)
            body = runtime.status()['fatigue']
            self.assertFalse(body['valid'])
            self.assertEqual(body['state'], 'integer_reference_mismatch')
            self.assertFalse(body['integer_reference_equal'])
            self.assertEqual(body['ps_scores'], [1., 0., 0.])
        finally:
            runtime.close()

    def test_network_round_trip_preserves_provenance_and_disconnect_clears(self):
        from z20_compute.feature_runtime import FeatureRuntime
        from z20_compute.service import BoardSession, FeaturePublisher
        class Classifier:
            version = "teacher-copy-v1"
            def predict(self, values, *, backend):
                return SimpleNamespace(valid=True, class_id=2, scores=np.array([0., 1., sum(values)]),
                    state="prediction", model_version=self.version, backend="test_adapter")
        runtime = FeatureRuntime({"fatigue": Classifier()})
        left, right = socket.socketpair()
        board, client = BoardSession(left, runtime), FeaturePublisher(right)
        try:
            board.start(); client.start()
            client.offer_features("fatigue", [1.] * 20, window_id="recording-1:8",
                feature_version="fatigue-calibrated-de20-v1", source="recorded:lemon")
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                board.pump()
                if client.results.get("fatigue") is not None: break
                time.sleep(.005)
            body = client.results.get("fatigue").body
            self.assertEqual(body["class_id"], 2)
            self.assertEqual(body["window_id"], "recording-1:8")
            self.assertEqual(body["source"], "recorded:lemon")
            self.assertEqual(body["feature_version"], "fatigue-calibrated-de20-v1")
            client.close()
            deadline = time.monotonic() + 1
            while runtime.status()["fatigue"]["valid"] and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertFalse(runtime.status()["fatigue"]["valid"])
        finally:
            client.close(); board.close(); runtime.close()

    def test_duplicate_windows_versions_old_sessions_and_expiry(self):
        from z20_compute.feature_runtime import FeatureRuntime
        clock = [10.]
        runtime = FeatureRuntime({}, now=lambda: clock[0])
        try:
            first = feature()
            self.assertTrue(runtime.submit_features(first))
            self.assertFalse(runtime.submit_features(dataclasses.replace(first, sequence=2)))
            self.assertFalse(runtime.submit_features(dataclasses.replace(first, session="other")))
            runtime.disconnect_eeg()
            self.assertTrue(runtime.submit_features(dataclasses.replace(first, session="other")))
            deadline = time.monotonic() + 1
            while not runtime.status()["fatigue"].get("window_id") and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertEqual(runtime.status()["fatigue"]["state"], "model_unavailable")
            clock[0] += 25
            runtime.poll()
            self.assertEqual(runtime.status()["fatigue"]["state"], "expired")
        finally:
            runtime.close()


if __name__ == "__main__": unittest.main()
