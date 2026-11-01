"""Optional image mode hosted by the existing HDMI owner."""
import time
import numpy as np
from types import SimpleNamespace
from .session import VisionSession,DEMO_MODES
from .keys import VisionKey,SignalKeys
from .pl_processor import PLProcessor
from .sources import OV5640Source
from .tobii_owner import TobiiImages
from .pupil import PupilDetector
from .presentation import Presenter
from .worker import VisionWorker
from .continuous import ContinuousVideo


class _TobiiView:
    """Worker view; the enclosing image session owns the USB lifetime."""
    def __init__(self,owner,generation):self.owner=owner;self.generation=generation
    def read(self,now):
        self.owner.generation=self.generation
        return self.owner.read(now)
    def close(self):pass


class VisionAddon:
    def __init__(self,overlay,config,eye_directory):
        if overlay.ip_dict.get('vision_keys_0',{}).get('phys_addr')!=0x43c40000:
            raise RuntimeError('Vision keys HWH mismatch')
        self.gpio=overlay.vision_keys_0;self.gpio.write(4,3)
        self.signal=None;self.signal_mode=False
        if config.get('signal_pages'):
            from .signal_runtime import SignalRuntime
            self.signal=SignalRuntime(overlay,config)
        self.key=SignalKeys(self.gpio.read(0)) if self.signal else VisionKey(self.gpio.read(0))
        self.continuous=ContinuousVideo(overlay.vision_core_0,config['camera_library']) if config.get('streaming') else None
        self.processor=None if self.continuous else PLProcessor(overlay)
        self.detector=PupilDetector(config.get('cascade_root'))
        self.presenter=Presenter(config.get('font'))
        self.session=VisionSession(enabled_modes=config.get('enabled_image_modes',DEMO_MODES));self.active=False;self.worker=None
        self.config=config;self.eye_directory=eye_directory
        self.pending=False;self.tobii=None

    @property
    def streaming(self):
        return not self.signal_mode and self.continuous is not None and self.session.source=='ov5640'

    def factory(self,name,generation):
        if name=='ov5640':return OV5640Source(self.config['camera_library'],generation)
        if self.tobii is None:
            self.tobii=TobiiImages(generation,shared_directory=self.eye_directory,binary=self.config['tobii_binary'])
        return _TobiiView(self.tobii,generation)

    def poll_key(self,now,allow=True):
        event=self.key.feed(self.gpio.read(0),now)
        if not event or not allow:return False
        if event=='signal':
            if not self.signal_mode:self.signal.pages.leave()
            self.signal_mode=True;self.active=True;self.signal.next();self.pending=True;return True
        if self.signal_mode:
            self.signal.leave();self.signal_mode=False;self.active=False
        if self.active:self.session.next_mode()
        else:
            self.active=True;self.session.index=self.session.enabled_indices[0];self.session.reset('waiting')
            if not self.continuous:self.worker=VisionWorker(self.factory,self.processor,self.detector)
        if self.continuous:self.pending=True
        else:self.worker.select(self.session.snapshot())
        return True

    def service(self,now):
        if self.signal_mode:
            if self.pending:
                if self.worker:self.worker.close();self.worker=None
                if self.continuous:self.continuous.close()
                if self.tobii:self.tobii.close();self.tobii=None
                self.pending=False
            self.signal.service(now);return
        if not self.continuous:return
        if self.pending:
            if self.streaming:
                if self.worker:self.worker.close();self.worker=None
                self.continuous.start(self.session.index)
            else:
                self.continuous.close()
                if self.worker is None:
                    self.worker=VisionWorker(self.factory,SimpleNamespace(backend='PS OpenCV pupil'),self.detector)
                self.worker.select(self.session.snapshot())
            self.pending=False
        if self.streaming:self.continuous.service()

    def snapshot(self,now):
        if self.signal_mode:return self.signal.snapshot(now)
        result,error=self.worker.snapshot(now) if self.worker else (None,None)
        row=self.session.snapshot()
        if self.streaming:
            row.update(active=self.active,reason='live' if self.continuous.active else 'waiting',
                       pupil_backend='PS OpenCV contour/ellipse',**self.continuous.snapshot())
            return row
        row.update(active=self.active,reason=error or ('live' if result else 'waiting'),
                   processing_backend='PS OpenCV pupil / full source resolution' if row['mode']=='pupil' else self.processor.backend,
                   pupil_backend='PS OpenCV contour/ellipse',
                   frame_sequence=result['sequence'] if result else None,
                   age_seconds=now-result['captured'] if result else None)
        return row

    def compose(self,buffer,now):
        if self.signal_mode:self.signal.compose(buffer,now);return
        result,error=self.worker.snapshot(now)
        snapshot=self.snapshot(now)
        rgb=self.presenter.render(snapshot,result['rgb'] if result else None,
            result.get('pupils') if result else None,
            result['backend'] if result else ('PS OpenCV pupil' if self.continuous else self.processor.backend))
        np.copyto(buffer,rgb[...,::-1]);buffer.flush()

    def leave(self,pl_reset=False):
        if self.signal:self.signal.leave()
        self.signal_mode=False
        if self.worker:self.worker.close(pl_reset=pl_reset);self.worker=None
        if self.continuous:self.continuous.close(pl_reset=pl_reset)
        if self.tobii:self.tobii.close();self.tobii=None
        self.pending=False
        self.active=False;self.session.reset('closed')

    def close(self,pl_reset=False):
        self.leave(pl_reset=pl_reset)
        if self.signal:self.signal.close();self.signal=None
        if self.processor:self.processor.close(pl_reset=pl_reset)
