"""Single camera owner, local audio producer and one shared HDMI/HTTP frame."""
import hashlib
import json
from pathlib import Path
import threading
import time
import numpy as np
from .audio import sound_features
from .audio_file import read_pcm,signal_analysis
from .headless_display import HeadlessDisplay
from .headless_preview import publish_frame
from .headless_keys import KeyGestures
from .training import PREPROCESSORS


class HeadlessPipeline:
    def __init__(self,runtime,snapshot,*,assets,preview,media_root=None,sound_root=None,
                 hdmi=False,keys=False,camera=None,media=None,display=None,renderer=None,
                 stereo=None,record_pairs=None,visual_state=None,visual_decoder=None,map_renderer=None,map_mode='original'):
        self.runtime,self.snapshot=runtime,snapshot
        self.assets,self.preview=Path(assets),Path(preview)
        self.media_root=Path(media_root) if media_root else None
        self.sound_root=Path(sound_root) if sound_root else None
        self.camera,self.media,self.display=camera,media,display
        self.renderer=renderer or HeadlessDisplay(self.assets/'glyphs.npz')
        self.lock,self.stopped=threading.Lock(),threading.Event()
        self.image,self.image_time,self.analysis=None,0.,None
        self.errors,self.threads={},[]
        self.key_input=None;self.gestures=KeyGestures();self.selection=0
        self.frames,self.display_matches,self.camera_frames,self.audio_windows=0,0,0,0
        self.freeze_frame=None
        self.stereo,self.record_pairs=stereo,Path(record_pairs) if record_pairs else None
        self.cloud_points,self.cloud_payload=None,None
        self.recorded_pairs=0
        self.visual=None
        if map_mode not in ('original','pl'):raise ValueError('map mode')
        if map_mode=='pl' and map_renderer is None:raise ValueError('PL map renderer is required')
        self.map_renderer,self.map_mode,self.map_generation=map_renderer,map_mode,0
        if visual_state is not None:
            from .visual_pipeline import VisualPipeline
            self.visual=VisualPipeline(self,visual_state,decoder=visual_decoder)
        if hdmi and self.display is None:
            from .isolated_hdmi import NavigatorOverlay
            self.display=NavigatorOverlay()
        if keys:
            from .fixed_scene_keys import NavigatorKeys
            self.key_input=NavigatorKeys()

    def start(self):
        targets=[self._render_loop]
        if self.media_root is not None or self.camera is not None:targets.append(self._vision_loop)
        if self.sound_root is not None:targets.append(self._audio_loop)
        for target in targets:
            thread=threading.Thread(target=target,daemon=True,name=target.__name__)
            self.threads.append(thread);thread.start()

    def status(self):
        with self.lock:
            return dict(frames=self.frames,display_matches=self.display_matches,camera_frames=self.camera_frames,
                audio_windows=self.audio_windows,errors=self.errors.copy(),
                map_mode=self.map_mode,map_available=self.map_renderer is not None,
                calibration_loaded=self.stereo is not None,recorded_pairs=self.recorded_pairs,
                camera_pairing='single_left_camera' if self.visual is not None else 'completion_timestamp_5ms',
                last_pair_skew_ns=getattr(getattr(self.camera,'reader',None),'last_pair_skew_ns',None),
                physical_keys_open=self.key_input is not None,physical_key_presses_verified=False)

    def set_map_mode(self,mode):
        if mode not in ('original','pl') or (mode=='pl' and self.map_renderer is None):raise ValueError('map mode unavailable')
        with self.lock:
            self.map_mode=mode;self.map_generation+=1
        return mode

    def cloud_detail(self):
        entry=self.runtime.environment_status().get('cloud',{})
        with self.lock:
            if not entry.get('valid') or self.cloud_points is None:return dict(valid=False,points=[])
            points=self.cloud_points[::max(1,(len(self.cloud_points)+2199)//2200)]
            return dict(valid=True,metadata=self.cloud_payload,points=points.tolist())

    def cloud_file(self):
        entry=self.runtime.environment_status().get('cloud',{})
        if not entry.get('valid'):return None
        with self.lock:
            if self.cloud_payload is None:return None
            path=self.preview.parent/'clouds'/self.cloud_payload['artifact_id']/'cloud.ply'
            return path.read_bytes() if path.is_file() and path.stat().st_size<4*1024*1024 else None

    def poll_keys(self):
        if self.key_input:
            for event in self.gestures.update(*self.key_input.read_pressed(),now=time.monotonic()):
                self.runtime.apply_key(event)

    def audio_detail(self):
        with self.lock:return self.analysis

    def _publish(self,task,*,valid,state,source,frame_id,payload=None,model='prepared-v1'):
        self.runtime.publish_environment(dict(task=task,valid=valid,state=state,source=source,
            frame_id=str(frame_id),payload=payload,model_version=model,reason=state))

    def _vision_loop(self):
        from .person_dog_camera_scene import photo_input_rgb,camera_scene,PHOTO_CAPTURE_STEP
        from .video_timeline import VideoTimeline
        try:
            if self.camera is None:
                from .stereo_live import StereoUIO
                matches=[p for p in Path('/sys/class/uio').glob('uio*') if (p/'name').read_text().strip()=='z20-video-observer']
                if len(matches)!=1:raise ValueError('expected one camera observer')
                options=(dict(camera_index=0) if self.visual is not None else
                    dict(independent_slots=True,max_pair_skew_ns=5_000_000))
                self.camera=StereoUIO('/dev/'+matches[0].name,matches[0]/'maps',
                    sample_step=PHOTO_CAPTURE_STEP,**options)
            if self.visual is not None:
                from .person_dog_camera_scene import main_input_rgb
                while not self.stopped.is_set():
                    snap=self.camera.latest()
                    if snap is not None:
                        with self.lock:
                            self.image=main_input_rgb(snap.pixels);self.image_time=time.monotonic()
                            self.camera_frames+=1;self.visual.camera_frame_id=str(snap.sequence)
                    # PL capture remains autonomous. The single-shot spatial
                    # mode needs fresh snapshots, not a second full-rate CPU
                    # video copy competing with JPEG/HDMI on Cortex-A9.
                    self.stopped.wait(.1)
                return
            if self.media is None:
                from .native_person_dog import NativeMedia
                self.media=NativeMedia(self.media_root/'libperson_dog.so')
            gallery=json.loads((self.media_root/'photos/gallery.json').read_text(encoding='utf-8'))['images']
            self.media.load_photos([self.media_root/'photos'/('scene%d.png'%i) for i in range(3)])
            timeline=VideoTimeline(json.loads((self.media_root/'video/annotations.json').read_text(encoding='utf-8')))
            video_mode=False;last_analysis=0.;last_capture=time.monotonic();tick=0;waiting=False
            last_depth,last_record=0.,0.
            for task in ('depth','cloud'):
                self._publish(task,valid=False,state='waiting_for_fresh_frame' if self.stereo else 'uncalibrated',
                    source='live:stereo',frame_id='initial')
            self._publish('adda',valid=False,state='prepared',source='local:interface_only',frame_id='initial')
            while not self.stopped.is_set():
                with self.runtime.lock:
                    nav=self.runtime.navigation;use_video=nav.page=='person_dog' and nav.detail==1
                if use_video!=video_mode:
                    self._publish('person_dog',valid=False,state='mode_changed',source='live:vision',frame_id='mode_changed')
                    with self.lock:self.image,self.image_time=None,0.
                    if use_video:self.media.open_video(self.media_root/'video/playback.avi')
                    video_mode=use_video
                snap=self.camera.latest()
                if snap is not None:
                    rgb=photo_input_rgb(snap.pixels);last_capture=time.monotonic();waiting=False
                    with self.lock:self.camera_frames+=1
                    if not use_video:
                        with self.lock:self.image,self.image_time=rgb,last_capture
                    if self.stereo is not None or self.record_pairs is not None:
                        from .stereo_board import CAPTURE_MODE,prepare_pair,record_pair
                        pair=prepare_pair(snap.pixels)
                        if self.record_pairs is not None and self.recorded_pairs<20 and last_capture-last_record>=2:
                            record_pair(self.record_pairs,pair,sequence=snap.sequence,captured_ns=snap.captured_ns)
                            self.recorded_pairs+=1;last_record=last_capture
                        if self.stereo is not None and last_capture-last_depth>=1:
                            result=self.stereo.process(pair,capture_mode=CAPTURE_MODE);last_depth=last_capture
                            fresh=time.monotonic_ns()-snap.captured_ns<2_000_000_000
                            valid=fresh and result.distance_m is not None
                            self._publish('depth',valid=valid,state='measurement' if valid else 'invalid_disparity',
                                source='live:stereo',frame_id='camera:%d'%snap.sequence,model='native-StereoBM-v1',
                                payload=dict(distance_m=result.distance_m,units='m',valid_points=result.valid_points,
                                    calibration_id=self.stereo.metadata['calibration_id'],capture_mode=CAPTURE_MODE) if valid else None)
                            if valid:
                                folder=self.preview.parent/'clouds'
                                payload=self.stereo.export(folder,result,sequence=snap.sequence)
                                with self.lock:self.cloud_points=result.xyz[result.valid_mask];self.cloud_payload=payload
                                self._publish('cloud',valid=True,state='measurement',source='live:stereo',
                                    frame_id='camera:%d'%snap.sequence,payload=payload,model='native-StereoBM-v1')
                                # Only generated, known filenames are removed; keep the last two exports.
                                exports=sorted(folder.glob('frame_*'),key=lambda p:p.stat().st_mtime)
                                for old in exports[:-2]:
                                    if old.is_dir() and old.name[6:].isdigit():
                                        for name in ('cloud.ply','snapshot.json'):
                                            if (old/name).is_file():(old/name).unlink()
                                        old.rmdir()
                            else:
                                with self.lock:self.cloud_points,self.cloud_payload=None,None
                                self._publish('cloud',valid=False,state='invalid_disparity',source='live:stereo',frame_id='camera:%d'%snap.sequence)
                if use_video:
                    decoded=self.media.next_video()
                    if decoded is None:
                        self.media.open_video(self.media_root/'video/playback.avi');continue
                    rgb,timestamp=decoded;scene=timeline.at(timestamp)
                    with self.lock:self.image,self.image_time=rgb,time.monotonic()
                    tick+=1
                    payload=None if scene is None else dict(interaction=scene['interaction'],
                        method='reviewed_video_annotations',geometry=scene.get('geometry'),
                        geometry_kind='reference_size_estimate',display_boxes=[scene['boxes'][k] for k in ('person','dog')],
                        source_time_s=timestamp,camera_depth_m=None)
                    self._publish('person_dog',valid=payload is not None,state='annotation_replay' if payload else 'unrecognized',
                        source='registered:video_file',frame_id='video:%d'%tick,payload=payload,model='reviewed-timeline-v1')
                    self.stopped.wait(.035)
                elif snap is not None and time.monotonic()-last_analysis>=.5:
                    last_analysis=time.monotonic()
                    result=camera_scene(rgb,self.media,gallery,captured_ns=snap.captured_ns)
                    scene=result['scene'];payload=None
                    if scene is not None:
                        payload=dict(interaction=scene['interaction'],method='registered_photo',
                            geometry=scene.get('geometry'),geometry_kind='reference_size_estimate',
                            display_boxes=result['display_boxes'],camera_depth_m=None,
                            inliers=result['match'].get('inliers',0))
                    self._publish('person_dog',valid=payload is not None,state='registered_photo' if payload else 'unrecognized',
                        source='live:camera_photo_registration',frame_id='camera:%d'%snap.sequence,payload=payload,model='ORB-RANSAC-v1')
                if time.monotonic()-last_capture>2 and not waiting:
                    self._publish('person_dog',valid=False,state='waiting_for_fresh_frame',source='live:camera',frame_id='waiting')
                    waiting=True
                self.stopped.wait(.005)
        except Exception as exc:
            with self.lock:self.errors['vision']=type(exc).__name__+': '+str(exc)
            self._publish('person_dog',valid=False,state='source_unavailable',source='live:camera',frame_id='fault')
            for task in ('depth','cloud'):
                self._publish(task,valid=False,state='source_unavailable',source='live:stereo',frame_id='fault')

    def _audio_loop(self):
        try:
            if self.visual is not None:return self.visual.audio_loop()
            manifest=json.loads((self.sound_root/'manifest.json').read_text(encoding='utf-8'))
            samples=[next(row for row in manifest['windows'] if row['class_id']==label) for label in range(3)]
            previous=None;counter=0
            while not self.stopped.is_set():
                with self.runtime.lock:
                    nav=self.runtime.navigation
                    if nav.page=='sound':self.selection=nav.detail%3
                    selection=self.selection
                if previous!=selection:
                    self.runtime.invalidate_local('sound');previous=selection
                row=samples[selection];path=self.sound_root/row['file']
                if hashlib.sha256(path.read_bytes()).hexdigest()!=row['pcm_sha256']:raise ValueError('audio sample hash mismatch')
                pcm=read_pcm(path);detail=signal_analysis(pcm);counter+=1
                detail.update(source_file=path.name,expected_class=selection,source_group=row['group'])
                with self.lock:self.analysis=detail;self.audio_windows+=1
                self._publish('audio',valid=True,state='recorded_file_analysis',source='recorded:'+path.name,
                    frame_id='audio:%d'%counter,payload=dict(rms=detail['rms'],dbfs=detail['dbfs'],
                        peak_frequency_hz=detail['peak_frequency_hz'],playback_started=False,clip_id=path.name),model='PCM-FFT1024-v1')
                try:features=sound_features(pcm)
                except ValueError as exc:
                    self.runtime.submit_local('sound',None,feature_version=PREPROCESSORS['sound'],window_id='audio:%d'%counter,
                        source='recorded:'+path.name,valid=False,quality=0.,reason=str(exc))
                else:
                    self.runtime.submit_local('sound',features,feature_version=PREPROCESSORS['sound'],window_id='audio:%d'%counter,
                        source='recorded:'+path.name)
                self.stopped.wait(1.)
        except Exception as exc:
            with self.lock:self.errors['audio']=type(exc).__name__+': '+str(exc)
            self._publish('audio',valid=False,state='source_unavailable',source='recorded:board_file',frame_id='fault')

    def _render_loop(self):
        try:
            if self.visual is not None:return self.visual.render_loop()
            while not self.stopped.is_set():
                with self.runtime.lock:
                    state=self.snapshot()
                    version=self.runtime.navigation.version
                with self.lock:
                    image=self.image if time.monotonic()-self.image_time<2 else None
                    analysis=self.analysis
                    points=self.cloud_points
                    cloud_metadata=dict(self.cloud_payload or {})
                    map_mode,map_generation=self.map_mode,self.map_generation
                frozen=state['page']=='overview' and state['detail']==1
                if frozen and self.freeze_frame is not None:
                    frame=self.freeze_frame.copy()
                    self.renderer.font.text(frame,'预览已冻结 · 后台继续',40,110,size=28)
                else:
                    frame=self.renderer.render(state,image=image,analysis=analysis,
                        cloud_points=points if state.get('environment',{}).get('cloud',{}).get('valid') else None)
                    if (state['page']=='cloud' and map_mode=='pl' and points is not None
                            and state.get('environment',{}).get('cloud',{}).get('valid')):
                        from .visual_wire import GeometryFrame
                        try:
                            bounded=points[::max(1,(len(points)+65535)//65536)]
                            geometry=GeometryFrame(bounded,units=cloud_metadata.get('units','m'),
                                frame_id=cloud_metadata.get('artifact_id',''),
                                metric_verified=bool(cloud_metadata.get('metric_verified',False)))
                            frame,_=self.map_renderer.render_geometry(geometry,view=state['detail'])
                        except Exception as exc:
                            with self.lock:
                                self.errors['map']=type(exc).__name__+': '+str(exc)
                                self.map_mode='original';self.map_generation+=1
                    self.freeze_frame=frame.copy()
                with self.runtime.lock:
                    if version!=self.runtime.navigation.version:continue
                with self.lock:
                    if map_generation!=self.map_generation:continue
                equal=None
                if self.display is not None:
                    self.display.show(frame.tobytes());equal=self.display.readback()==frame.tobytes()
                    if not equal:raise RuntimeError('display buffer differs from unified frame')
                publish_frame(self.preview,frame,result=dict(page=state['page'],detail=state['detail'],
                    frozen=frozen,renderer='unified-nine-page-v1'),display_equal=equal)
                with self.lock:
                    self.frames+=1
                    if equal:self.display_matches+=1
                self.stopped.wait(.4)
        except Exception as exc:
            with self.lock:self.errors['display']=type(exc).__name__+': '+str(exc)

    def close(self):
        self.stopped.set()
        for thread in self.threads:thread.join(4)
        if any(thread.is_alive() for thread in self.threads):raise RuntimeError('pipeline workers still own resources')
        try:
            frame=self.renderer.render(dict(page='overview',detail=0,results={},environment={},connected=False))
            self.renderer.font.text(frame,'服务已停止',40,140,size=40)
            if self.display is not None:self.display.show(frame.tobytes())
            publish_frame(self.preview,frame,result=dict(state='stopped',valid=False))
        except Exception as exc:
            with self.lock:self.errors['stop_display']=type(exc).__name__
        for resource in (self.key_input,self.camera,self.media,self.display):
            if resource is not None:resource.close()
