"""Adapter into the existing camera/NPU/display owners; never starts a second one."""
import hashlib,json,time
from pathlib import Path
import numpy as np
from collections import deque
from .audio import sound_features
from .audio_file import read_pcm
from .visual_audio import SequentialSpectrum
from .visual_display import DemoDisplay
from .training import PREPROCESSORS


class VisualPipeline:
    def __init__(self,pipeline,state,*,decoder=None):
        self.pipeline,self.state=pipeline,state
        self.display=DemoDisplay(pipeline.renderer.font,**({'decoder':decoder} if decoder else {}))
        self.camera_frame_id=None

    def camera_ppm(self):
        p=self.pipeline
        with p.lock:
            if p.image is None or time.monotonic()-p.image_time>2:return None
            rgb=p.image.copy();frame_id=self.camera_frame_id
        height,width=rgb.shape[:2]
        return dict(frame_id=frame_id,capture_mode='navigator-q4-left-rgb-v1',camera_index=0,width=width,height=height,
                    source='live:Z20_camera',metric_verified=False),(
                    ('P6\n%d %d\n255\n'%(width,height)).encode()+rgb.tobytes())

    def audio_loop(self):
        p=self.pipeline
        rows=None
        previous=None;spectrum=None;features=None;window_id=None;last_sequence=-1;submitted_cycle=-1
        history=deque(maxlen=40)
        external_key=None;frozen_sound=None
        while not p.stopped.is_set():
            view=self.state.snapshot();now=time.monotonic()
            if view['menu'] or view['mode'] not in ('spectrum','npu'):
                p.stopped.wait(.05);continue
            if view['mode']=='npu' and view['sample_index']<2:
                task=('fatigue','emotion')[view['sample_index']]
                live=p.runtime.status().get(task,{})
                if live.get('origin')=='network' and live.get('features'):
                    self.state.publish('npu',dict(live,event='completed',task=task),epoch=view['epoch'])
                else:
                    trace=dict(task=task,valid=False,state='waiting_for_live_eeg',event=None,
                        source='live:Z15',reason='等待 Z15 实时脑电特征',class_id=None,scores=None,
                        features=[],quantized_features=[],timing=None,window_id=None,
                        integer_reference_equal=None)
                    self.state.publish('npu',trace,epoch=view['epoch'])
                p.stopped.wait(.05);continue
            incoming=view.get('sound_input') if view['mode']=='npu' else None
            if incoming:
                key=(view['epoch'],incoming['window_id'])
                if key!=external_key:
                    external_key=key;frozen_sound=None
                    p.runtime.invalidate_local('sound')
                    p.runtime.submit_local('sound',incoming['vector'],feature_version=PREPROCESSORS['sound'],
                        window_id=incoming['window_id'],source=incoming['source'],valid=incoming['valid'],reason=incoming['reason'])
                result=p.runtime.status().get('sound',{})
                if result.get('window_id')==incoming['window_id'] and result.get('state') not in ('expired','disconnected'):
                    frozen_sound=dict(result,event='completed',task='sound',frozen=True)
                trace=frozen_sound or dict(task='sound',source=incoming['source'],window_id=incoming['window_id'],valid=False,event='submitted')
                self.state.publish('npu',trace,epoch=view['epoch']);p.stopped.wait(.05);continue
            if rows is None:
                manifest=json.loads((p.sound_root/'manifest.json').read_text(encoding='utf-8'))
                rows=[next(r for r in manifest['windows'] if r['class_id']==label) for label in range(3)]
            key=(view['epoch'],view.get('sound_sample_index',0) if view['mode']=='npu' else view['sample_index'])
            if key!=previous:
                row=rows[key[1]];path=p.sound_root/row['file']
                if hashlib.sha256(path.read_bytes()).hexdigest()!=row['pcm_sha256']:raise ValueError('recorded PCM hash mismatch')
                pcm=read_pcm(path);source='recorded:'+row['file']
                spectrum=SequentialSpectrum(pcm,source=source,started=now)
                previous=key;last_sequence=-1;window_id='visual:%d:%d'%key
                submitted_cycle=-1
                history.clear()
                p.runtime.invalidate_local('sound')
                try:features=sound_features(pcm)
                except ValueError as exc:
                    features=None
                    invalid_reason=str(exc)
            detail=spectrum.at(now)
            cycle=detail['window_sequence']//20
            if cycle!=submitted_cycle:
                window_id='visual:%d:%d:%d'%(key[0],key[1],cycle)
                accepted=p.runtime.submit_local('sound',features,feature_version=PREPROCESSORS['sound'],window_id=window_id,
                    source=source,valid=features is not None,quality=1. if features is not None else 0.,
                    reason='ok' if features is not None else invalid_reason)
                submitted_cycle=cycle
                if accepted:
                    model=p.runtime.models.get('sound')
                    self.state.publish('npu',dict(task='sound',valid=False,window_id=window_id,source=source,
                        event='submitted',event_monotonic=now,scores=None,
                        backend=p.runtime.backend.name if p.runtime.backend else 'PS_integer_reference',
                        features=features.tolist() if features is not None else [],
                        quantized_features=model.quantize_input(features).tolist() if model and features is not None else []),epoch=key[0])
            if detail['window_sequence']!=last_sequence:
                history.append(dict(window_sequence=detail['window_sequence'],sample_offset=detail['sample_offset'],band_values=detail['band_values']))
                detail['history']=list(history)
                self.state.publish('spectrum',detail,epoch=key[0]);last_sequence=detail['window_sequence']
            result=p.runtime.status().get('sound',{})
            if result.get('window_id')==window_id:
                model=p.runtime.models.get('sound')
                trace=dict(result,task='sound',event='completed',event_monotonic=result.get('completed_monotonic',now),features=features.tolist() if features is not None else [],
                    quantized_features=model.quantize_input(features).tolist() if model and features is not None else [])
                self.state.publish('npu',trace,epoch=key[0])
            p.stopped.wait(.025)

    def render_loop(self):
        p=self.pipeline;last_key=None;last_preview=0.
        from .headless_preview import publish_frame
        from .video import AnalysisWorker
        # PNG compression never owns or waits on the HDMI ring. Frames returned
        # by DemoDisplay are owned immutable snapshots until a new allocation.
        worker=AnalysisWorker(lambda job:publish_frame(p.preview,job[0],result=job[1],display_equal=job[2]))
        try:
            while not p.stopped.is_set():
                result=worker.result()
                if result is not None and not result.valid:raise RuntimeError('visual preview failed: '+result.state)
                state=self.state.snapshot();frame,key=self.display.render(state,self.state.latest())
                if key!=last_key:
                    if p.display is not None:p.display.show(frame.tobytes())
                    with p.lock:p.frames+=1
                    last_key=key
                now=time.monotonic()
                if now-last_preview>=1:
                    equal=p.display.readback()==frame.tobytes() if p.display is not None else None
                    if equal is False:raise RuntimeError('visual display readback differs')
                    worker.submit(state['frame_sequence'],(frame,dict(mode=state['mode'],epoch=state['epoch'],
                        renderer='four-mode-visual',frame_sequence=state['frame_sequence']),equal))
                    last_preview=now
                    if equal:
                        with p.lock:p.display_matches+=1
                p.stopped.wait(.005)
        finally:worker.close()
