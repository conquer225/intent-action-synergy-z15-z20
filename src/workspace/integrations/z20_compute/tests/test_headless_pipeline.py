import hashlib
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
import wave
import numpy as np
from z20_compute.feature_runtime import FeatureRuntime
from z20_compute.headless_keys import Navigation
from z20_compute.headless_pipeline import HeadlessPipeline


class PipelineTests(unittest.TestCase):
    def test_single_camera_and_local_audio_continue_across_disconnect_then_release_resources(self):
        class Camera:
            closed=0;sequence=0
            def latest(self):
                self.sequence+=1
                return SimpleNamespace(sequence=self.sequence,captured_ns=time.monotonic_ns(),pixels=np.zeros((180,320,3),np.uint8))
            def close(self):self.closed+=1
        class Media:
            closed=0;loads=0
            def load_photos(self,paths):self.loads+=1
            def match(self,rgb):return dict(scene_id=None,homography=None,inliers=0,state='unrecognized')
            def close(self):self.closed+=1
        class Display:
            closed=0;frame=None
            def show(self,frame):self.frame=frame
            def readback(self):return self.frame
            def close(self):self.closed+=1
        class Renderer:
            font=SimpleNamespace(text=lambda *args,**kwargs:None)
            def render(self,*args,**kwargs):return np.full((720,1280,3),241,np.uint8)
        class Stereo:
            metadata={'calibration_id':'a'*64}
            def process(self,pair,*,capture_mode):
                return SimpleNamespace(distance_m=1.,valid_points=1024,
                    xyz=np.ones((180,160,3),np.float32),valid_mask=np.ones((180,160),bool))
            def export(self,folder,result,*,sequence):
                return dict(artifact_id='frame_%d'%sequence,points=28800,metric=True,units='m',
                    calibration_id='a'*64,capture_mode='diagnostic')
        class Classifier:
            version='pipeline-diagnostic'
            def predict(self,values,*,backend):
                return SimpleNamespace(valid=True,class_id=1,scores=np.array([0.,2.,1.]),
                    state='prediction',model_version=self.version,backend='test_adapter')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'photos').mkdir();(root/'video').mkdir()
            (root/'photos/gallery.json').write_text(json.dumps(dict(images=[{}, {}, {}])))
            (root/'video/annotations.json').write_text(json.dumps(dict(format='z20-video-annotations-v1',
                image_size=[640,480],duration_s=1.,keyframes=[dict(time_s=0,visible=False),dict(time_s=1,visible=False)])))
            pcm=np.rint(np.sin(np.arange(16000)*2*np.pi*1000/16000)*6000).astype('<i2')
            source=root/'diagnostic.wav'
            with wave.open(str(source),'wb') as stream:
                stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(16000);stream.writeframes(pcm.tobytes())
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            (root/'manifest.json').write_text(json.dumps(dict(windows=[dict(class_id=i,file=source.name,
                pcm_sha256=digest,group='diagnostic-fixture') for i in range(3)])))
            runtime=FeatureRuntime({'sound':Classifier()},navigation=Navigation())
            camera,media,display=Camera(),Media(),Display()
            def snapshot():return dict(page=runtime.navigation.page,detail=runtime.navigation.detail,
                connected=False,results=runtime.status(),environment=runtime.environment_status())
            pipeline=HeadlessPipeline(runtime,snapshot,assets=root,preview=root/'frame.png',media_root=root,
                sound_root=root,camera=camera,media=media,display=display,renderer=Renderer(),stereo=Stereo())
            try:
                pipeline.start();deadline=time.monotonic()+2
                while (not runtime.status()['sound']['valid'] or pipeline.frames<1) and time.monotonic()<deadline:time.sleep(.01)
                self.assertTrue(runtime.status()['sound']['valid'])
                before=pipeline.status()['camera_frames'];runtime.disconnect_eeg();time.sleep(.15)
                self.assertGreater(pipeline.status()['camera_frames'],before)
                self.assertTrue(runtime.status()['sound']['valid'])
                self.assertGreater(pipeline.status()['display_matches'],0)
                self.assertEqual(media.loads,1)
                self.assertEqual(pipeline.status()['errors'],{})
                self.assertTrue(runtime.environment_status()['depth']['valid'])
                self.assertEqual(runtime.environment_status()['depth']['payload']['distance_m'],1.)
                self.assertTrue(pipeline.cloud_detail()['valid'])
            finally:pipeline.close();runtime.close()
            self.assertEqual((camera.closed,media.closed,display.closed),(1,1,1))
            self.assertFalse(runtime.status()['sound']['valid'])
            self.assertEqual(json.loads((root/'frame.json').read_text())['result']['state'],'stopped')


if __name__=='__main__':unittest.main()
