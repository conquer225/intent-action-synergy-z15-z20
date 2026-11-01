import json
import struct
import time
import unittest
from types import SimpleNamespace
import numpy as np
import threading
from z20_compute.protocol import Message,Decoder,encode


def depth(**changes):
    body=dict(task='depth',valid=True,state='measurement',source='live:stereo',
        model_version='native-stereo-v1',frame_id='camera:8',reason='ok',
        payload=dict(distance_m=1.25,units='m',calibration_id='a'*64,
                     capture_mode='quarter-gray-v1',valid_points=120))
    body.update(changes)
    return Message('environment','board',8,0,body)


class EnvironmentTests(unittest.TestCase):
    def test_nonstring_calibration_id_is_rejected_as_invalid_input(self):
        with self.assertRaises(ValueError):encode(depth(payload=dict(depth().body['payload'],calibration_id=123)))

    def test_late_connection_snapshot_includes_static_status_without_refreshing_expired_data(self):
        from z20_compute.feature_runtime import FeatureRuntime
        clock=[100.];runtime=FeatureRuntime({},now=lambda:clock[0])
        try:
            runtime.publish_environment(depth().body);runtime.poll()
            clock[0]+=4;runtime.publish_snapshot()
            messages=runtime.poll()
            self.assertEqual(len(messages),1)
            self.assertFalse(messages[0].body['valid'])
            self.assertEqual(messages[0].body['state'],'expired')
            self.assertEqual(runtime.environment_status()['depth']['age_seconds'],4.)
        finally:runtime.close()

    def test_new_local_sample_fences_a_slow_old_inference(self):
        from z20_compute.feature_runtime import FeatureRuntime
        from z20_compute.training import PREPROCESSORS
        entered,release=threading.Event(),threading.Event()
        class Classifier:
            version='slow-local-test';calls=0
            def predict(self,values,*,backend):
                self.calls+=1
                if self.calls==1:entered.set();release.wait(1)
                return SimpleNamespace(valid=True,class_id=1,scores=np.array([0.,2.,1.]),
                    state='prediction',model_version=self.version,backend='test')
        runtime=FeatureRuntime({'sound':Classifier()})
        try:
            options=dict(feature_version=PREPROCESSORS['sound'],source='recorded:test')
            runtime.submit_local('sound',[1.]*40,window_id='old',**options)
            self.assertTrue(entered.wait(1));runtime.invalidate_local('sound')
            self.assertFalse(runtime.status()['sound']['valid'])
            runtime.submit_local('sound',[2.]*40,window_id='new',**options);release.set()
            deadline=time.monotonic()+1
            while runtime.status()['sound'].get('window_id')!='new' and time.monotonic()<deadline:time.sleep(.005)
            self.assertEqual(runtime.status()['sound']['window_id'],'new')
            self.assertFalse(any(m.body.get('window_id')=='old' for m in runtime.poll()))
        finally:release.set();runtime.close()

    def test_versioned_result_requires_metric_calibration_and_clears_invalid_payload(self):
        wire=encode(depth())
        self.assertEqual(json.loads(wire[4:])['version'],2)
        self.assertEqual(Decoder().feed(wire),[depth()])
        for change in [dict(calibration_id=''),dict(distance_m=-1),dict(distance_m=float('nan')),
                       dict(units='pixels'),dict(valid_points=0)]:
            payload=dict(depth().body['payload'],**change)
            with self.subTest(change=change),self.assertRaises(ValueError):encode(depth(payload=payload))
        with self.assertRaises(ValueError):encode(depth(valid=False))
        self.assertEqual(Decoder().feed(encode(depth(valid=False,payload=None,state='uncalibrated')))[0].body['payload'],None)

    def test_local_environment_and_sound_survive_remote_eeg_disconnect_and_expire_locally(self):
        from z20_compute.feature_runtime import FeatureRuntime
        from z20_compute.training import PREPROCESSORS
        class Classifier:
            version='local-audio-test'
            def predict(self,values,*,backend):
                return SimpleNamespace(valid=True,class_id=1,scores=np.array([0.,2.,1.]),
                    state='prediction',model_version=self.version,backend='test_adapter')
        clock=[100.]
        runtime=FeatureRuntime({'sound':Classifier()},now=lambda:clock[0])
        try:
            self.assertTrue(runtime.publish_environment(depth().body))
            runtime.submit_local('sound',[1.]*40,feature_version=PREPROCESSORS['sound'],
                                 window_id='local:1',source='recorded:board_file')
            deadline=time.monotonic()+1
            while not runtime.status()['sound']['valid'] and time.monotonic()<deadline:time.sleep(.005)
            runtime.disconnect_eeg()
            self.assertTrue(runtime.status()['sound']['valid'])
            self.assertTrue(runtime.environment_status()['depth']['valid'])
            self.assertTrue(any(m.kind=='environment' for m in runtime.poll()))
            clock[0]+=4
            messages=runtime.poll()
            self.assertTrue(all(not m.body['valid'] for m in messages))
            self.assertIsNone(runtime.environment_status()['depth']['payload'])
            self.assertFalse(runtime.status()['sound']['valid'])
        finally:runtime.close()


if __name__=='__main__':unittest.main()
