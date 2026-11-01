"""Bounded latest-result worker: source acquisition and PL processing never block HDMI."""
import threading
import time
from .session import Frame


class VisionWorker:
    def __init__(self,factory,processor,pupil_detector):
        self.factory=factory;self.processor=processor;self.pupil_detector=pupil_detector
        self.lock=threading.Lock();self.stop=threading.Event();self.desired=None;self.result=None
        self.error=None;self.source=None;self.source_name=None;self.cleanup_error=None
        self.thread=threading.Thread(target=self._run,name='vision-latest',daemon=True)
        self.thread.start()

    def select(self,snapshot):
        with self.lock:self.desired=dict(snapshot);self.result=None;self.error=None

    def snapshot(self,now):
        with self.lock:
            result=self.result
            if result and not 0<=now-result['captured']<=1.5:result=None
            return result,self.error

    def _run(self):
        previous=None;last_time=None;last_sequence=None
        try:
            while not self.stop.is_set():
                with self.lock:wanted=dict(self.desired) if self.desired else None
                if not wanted:self.stop.wait(.025);continue
                token=wanted['generation']
                try:
                    if self.source_name!=wanted['source']:
                        if self.source:self.source.close()
                        self.source=None;self.source_name=None
                        self.source=self.factory(wanted['source'],token)
                        self.source_name=wanted['source']
                    self.source.generation=token
                    frame=self.source.read(time.monotonic())
                    if frame is None:self.stop.wait(.025);continue
                    now=time.monotonic()
                    if frame.source!=wanted['source'] or frame.generation!=token or not 0<=now-frame.captured<=1.5:
                        continue
                    if previous==token and (frame.sequence<=last_sequence or frame.captured<last_time):
                        continue
                    reset=previous!=token or last_time is None or frame.captured-last_time>1.5
                    pupils=None;backend=self.processor.backend
                    if wanted['mode']=='pupil':
                        pupils=self.pupil_detector.detect(frame.rgb)
                        # The presentation image must keep the same coordinates as
                        # the detector; pupil mode displays source-resolution RGB.
                        rgb=frame.rgb.copy()
                        backend='PS OpenCV pupil / full source resolution'
                    else:rgb=self.processor.process(frame.rgb,wanted['mode'],reset=reset)
                    row=dict(rgb=rgb,pupils=pupils,captured=frame.captured,
                             sequence=frame.sequence,generation=token,
                             source=frame.source,backend=backend)
                    with self.lock:
                        if self.desired and self.desired['generation']==token:
                            self.result=row;self.error=None
                    previous=token;last_time=frame.captured;last_sequence=frame.sequence
                except Exception as exc:
                    if getattr(exc,'owner',None) is not None:
                        self.source=exc.owner;self.cleanup_error=str(exc)
                        break
                    with self.lock:
                        self.result=None;self.error=type(exc).__name__+': '+str(exc)
                    if getattr(self.processor,'running',False):break
                    if self.source:
                        try:self.source.close()
                        except Exception as cleanup:
                            self.cleanup_error=str(cleanup);break
                    self.source=None;self.source_name=None;previous=None
                    self.stop.wait(1)
        finally:
            if self.source:
                try:self.source.close()
                except Exception as exc:
                    self.cleanup_error=str(exc)
                    with self.lock:self.error='Capture cleanup failed: '+str(exc)

    def close(self,pl_reset=False):
        self.stop.set();self.thread.join(timeout=5)
        if self.thread.is_alive():raise RuntimeError('Vision worker did not stop; retain its buffers')
        if self.cleanup_error:
            if not pl_reset:raise RuntimeError('Capture cleanup failed; retain buffers until PL reset: '+self.cleanup_error)
            self.source.release_after_reset()
            self.cleanup_error=None;self.source=None
