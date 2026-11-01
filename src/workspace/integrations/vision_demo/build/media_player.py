"""Finite silent HDMI session. Existing ARM acquisition stays running, PL is restored."""
import argparse
import ctypes as C
import fcntl
import hashlib
import json
import math
from pathlib import Path
import resource
import signal
import sys
import time

import numpy as np
from pynq import PL, Overlay, allocate
from chunk_cache import BoundedChunks
from prepare_chunks import decoder
from upload_server import write_json
from player_commands import PlayerCommands
from playback_policy import RecentSamples, session_deadline
from prewear import hdmi_preflight

BASE=Path(__file__).resolve().parent


def stop(*_):raise KeyboardInterrupt


def main():
    p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True)
    p.add_argument('--hdmi-candidate',action='store_true',help='Enable the opt-in native HDMI candidate')
    p.add_argument('--ssvep-runtime',type=Path,help='Candidate acquisition runtime directory')
    p.add_argument('--ssvep-port',type=int,default=9105)
    p.add_argument('--native-scan-library',type=Path)
    p.add_argument('--native-scan-sha256')
    args=p.parse_args()
    if args.state.resolve().parent!=BASE:raise ValueError('Foreign session path')
    state=json.loads(args.state.read_text())
    page_path=BASE/'system_page.json';status_path=BASE/'player_status.json'
    if state.get('unified_system'):
        page_path=Path('/dev/shm')/(BASE.name+'-system-page.json')
        status_path=Path('/dev/shm')/(BASE.name+'-player-status.json')
    sys.path.insert(0,state['eye_root']+'/src')
    from coexist_guard import CoexistGuard
    from calibration_worker import Worker
    root=Path(state['eye_root'])
    original,display=state['original_overlay'],state['display_overlay']
    guard=CoexistGuard(root,PL.bitfile_name,allow_acquisition_restart=True)
    report={'silent':True,'audio_output':False,'brain_services_stopped':False,
        'diagnostic_eye_only':state.get('eye_diagnostic') is True,'physical_control':False,'buffers_released':False,
        'original_restored':False,'new_frame_times':RecentSamples(),'eye_results':RecentSamples(256),'errors':RecentSamples(256)}
    locks,buffers=[],[]
    attempted=mapped=False
    source=eye=convert=watch=unified=brain=live_eye=rating_writer=buttons=stimulus=device_link=None
    live=state.get('live_system') is True
    commands=PlayerCommands(BASE.name,state['session_id']) if live else None
    eye_only=state.get('eye_only') is True
    if args.hdmi_candidate:
        if not (live and state.get('unified_system') and not eye_only and args.ssvep_runtime
                and args.native_scan_library and args.native_scan_sha256):
            raise ValueError('HDMI candidate requires a live unified session and its candidate runtime')
        if hashlib.sha256(args.native_scan_library.read_bytes()).hexdigest()!=args.native_scan_sha256:
            raise ValueError('Native scan candidate changed')
        sys.path.insert(0,str(args.ssvep_runtime.resolve()))
        from native_scan import NativeScan
        NativeScan(args.native_scan_library)
    if eye_only and not (live and state.get('unified_system')):
        raise ValueError('Eye-only check requires the unified live display')
    library=None;last_rating_event=None;live_eye_view=None
    audio=None;audio_video_frames=0;vision=None
    lib=C.CDLL(str(BASE/'libtobii_display.so'))
    lib.display_open.argtypes=[C.POINTER(C.c_uint32)]
    lib.display_open.restype=C.c_int
    lib.display_park.argtypes=[C.c_uint];lib.display_park.restype=C.c_int
    lib.display_index.restype=lib.display_frames.restype=lib.display_status.restype=C.c_uint32
    lib.display_close.restype=C.c_int
    current_status={'state':'starting','silent':True,'frame':0,'session_id':state['session_id']}
    def status(**values):
        current_status.update(values,updated_monotonic=time.monotonic())
        write_json(status_path,current_status)
    def start_eye(now):
        nonlocal live_eye,live_eye_view,eye_view,menu_page
        if stimulus and (stimulus.active or stimulus.pending):
            stimulus.stop();menu_page=-1
        if live_eye is None or live_eye.guide.phase in ('failed','selection'):
            if live_eye:
                report['eye_results'].append(live_eye.snapshot(now));live_eye.close()
            unified.controller._stop(now,'eye_calibration')
            unified.controller.selection.clear_pending()
            unified.controller.selection.selected=-1
            unified.controller.last_selection=None
            unified.controller._clear_mi()
            live_eye=EyeInputs(root);live_eye_view=None;eye_view={}
            unified.calibration_view=None
        elif live_eye.guide.phase=='positioning':live_eye.confirm_position(now)

    def stop_eye(now):
        nonlocal live_eye,live_eye_view,eye_view
        if live_eye:
            report['eye_results'].append(live_eye.snapshot(now));live_eye.close()
        live_eye=None;live_eye_view=None;eye_view={}
        unified.controller.selection.clear_pending();unified.controller.selection.selected=-1
        unified.controller.last_selection=None
        unified.controller._stop(now,'eye_stopped');unified.controller._clear_mi()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        for name in ('guardianloop-pl.lock','tobii_display.lock'):
            handle=open('/run/lock/'+name,'a');fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(handle)
        report['admission']=guard.verify()
        if state.get('hdmi_audio'):
            if not (live and state.get('unified_system')):
                raise ValueError('Audio requires the candidate unified live display')
            from page_audio import create_page_audio
            audio=create_page_audio(state['hdmi_audio'],display)
            report.update(silent=False,audio_output=True,audio_speaker_verified=False)
        if state.get('unified_system'):
            if live:
                sys.path.insert(0,str(BASE/'system_runtime'))
                from guardianloop_system.device_link import from_config,service_eye
                device_link=from_config(BASE/'eye_devices.json')
            from system_hdmi import UnifiedDisplay,RuntimeWatch,present_frame
            fitter=C.CDLL(str(BASE/'frame_fitter.so'))
            fitter.fit_bgr.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_void_p,C.c_int,C.c_int,C.c_int]
            fitter.fit_bgr.restype=C.c_int
            shell_cache=BASE/('menu-shells-portrait-audio.npz' if audio else 'menu-shells-portrait-live.npz') if live else None
            unified=UnifiedDisplay(state['eye_root'],fitter.fit_bgr,live=live,
                dimensions=(288,512) if live else (384,216),
                shell_cache=shell_cache if shell_cache and shell_cache.is_file() and not device_link else None,
                direction_idle_enabled=state.get('direction_idle_enabled',True),device_link=device_link)
            report.update(mode='live_readonly_hdmi' if live else 'scripted_hdmi_replay',live_eeg_connected=False,
                          live_gaze_connected=False,one_display_owner=True)
            if live:
                from guardianloop_system.live_inputs import BrainInputs,EyeInputs
                from guardianloop_system.media_library import MediaLibrary,RatingWriter
                library=MediaLibrary(BASE/'ratings.json');library.replace(state['playlist'])
                if not library.videos:raise ValueError('No prepared videos')
                unified.controller.video_count=len(library.videos)
                unified.controller.direction_requires_start=args.hdmi_candidate
                unified.controller.video_index=state.get('video_index',0)
                if not 0<=unified.controller.video_index<len(library.videos):raise ValueError('Invalid initial video')
                brain=None if eye_only else BrainInputs(availability=lambda:guard.acquisition_identity,hdmi_input=(
                    lambda page,now:stimulus.input(page,now) if stimulus else None))
                rating_writer=RatingWriter(library)
                initial_page=state.get('initial_page','video')
                if initial_page not in ('home','video'):raise ValueError('Invalid initial display page')
                unified.controller._enter(initial_page,time.monotonic())
                state['cache']=library.videos[unified.controller.video_index]['cache']
        for path,sha in state['hardware_hashes'].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:
                raise ValueError('Hardware/recovery artifact changed')
        source=BoundedChunks(state['cache'],loop=live)
        block=source.acquire(timeout=10)
        if block is None:raise ValueError('Empty cache')
        dimensions=(source.meta['width'],source.meta['height'])
        if unified and (dimensions not in ((640,360),(384,216),(288,512)) or source.meta['format']!='gl-bgr24-lz4-v1'):
            raise ValueError('Unified HDMI trial requires the verified compact BGR cache')
        if live and dimensions!=(288,512):raise ValueError('Live session requires prepared portrait-canvas cache')
        if not unified and dimensions==(384,216):
            raise ValueError('Central-display cache requires a unified display session')
        expander=None
        if source.meta['width']==640:
            expander=C.CDLL(str(BASE/'frame_expander.so'))
            expander.expand_bgr_360.argtypes=[C.c_void_p,C.c_void_p,C.c_int]
            expander.expand_bgr_360.restype=C.c_int
        elif source.meta['format']=='gl-yuv420-lz4-v1':
            libvideo=decoder(BASE/'frame_decoder.so');convert=libvideo.bgr_open()
            if not convert:raise ValueError('Color conversion unavailable')
        for _ in range(3):
            buffer=allocate(shape=(720,1280,3),dtype=np.uint8)
            buffer[:]=0;buffer[350:370,630:650]=255;buffer.flush();buffers.append(buffer)
        stimulus_frames=None
        if args.hdmi_candidate:
            from hdmi_stimulus import StimulusFrames
            from native_scan import preflight
            stimulus_frames=StimulusFrames(unified)
            report['native_preflight']=preflight(lib,stimulus_frames,buffers,30,args.native_scan_library)
            report['native_scan_sha256']=args.native_scan_sha256
        attempted=True;overlay=Overlay(display)
        required={'axi_vdma_0':0x43000000,'axi_vdma_1':0x43010000,
                  'live_osd_0':0x43c00000,'v_tc_0':0x43c10000}
        if any(overlay.ip_dict.get(name,{}).get('phys_addr')!=addr for name,addr in required.items()):
            raise ValueError('Display register map mismatch')
        mapped=True
        if not lib.display_open((C.c_uint32*3)(*[b.physical_address for b in buffers])) or not lib.display_park(0):
            raise ValueError('Display initialization failed')
        if unified:
            def checked_runtime():
                if PL.bitfile_name!=display:raise ValueError('Display PL ownership changed')
                guard.check_runtime()
            checked_runtime()
            watch=RuntimeWatch(checked_runtime)
            watch.check_ms=RecentSamples()
        if live:
            from buttons import Buttons
            buttons=Buttons()
        if live and state.get('vision_demo'):
            from vision_demo.addon import VisionAddon
            from vision_demo.eye_observer import observe_eye,can_enter
            vision=VisionAddon(overlay,state['vision_demo'],
                lambda:live_eye.worker.directory if live_eye and live_eye.worker.process.poll() is None else None)
        if args.hdmi_candidate:
            from hdmi_stimulus import HdmiStimulus
            from ssvep_cue_runtime import SSVEPCueBridge
            lib.Xil_In32.argtypes=[C.c_uint32];lib.Xil_In32.restype=C.c_uint32
            stimulus=HdmiStimulus(lib,buffers,unified,SSVEPCueBridge(args.ssvep_port),
                                 native_library=args.native_scan_library,frames=stimulus_frames)
            if state.get('hdmi_fixed_brightness_diagnostic') is True:
                # Exercise the real report transport without exposing a wearer to flicker.
                for patch in stimulus_frames.patches.values():patch[:]=(24,34,44)
        eye_attempts=0;runtime_paused=False
        if state.get('eye_diagnostic'):
            # This positioning diagnostic does not calibrate or drive physical controls.
            eye=Worker(root,220,160,diagnostic=True,locate=True)
            eye.command('locate')
            eye_attempts=1
        start=time.monotonic();deadline=session_deadline(state,live,start)
        cpu=time.process_time();presented=0;paused=False;last_command=None
        command_receipt=None
        last_check=last_status=0;due=start
        buffering=0;max_wait=0;scans=lib.display_frames()
        menu_page=-1;video_elapsed=0.;video_started=None;stage_times=RecentSamples();video_eof=False
        selected_index=unified.controller.video_index if live else None
        frame_period=1/source.meta['fps'];brain_view={};eye_view={}
        status_io_ms=RecentSamples();command_io_ms=RecentSamples()
        while deadline is None or time.monotonic()<deadline:
            now=time.monotonic()
            if watch and not watch.ready():
                if device_link:device_link.stop('运行检查暂停')
                if audio:audio.service(unified.controller,blocked=True)
                if PL.bitfile_name!=display:raise ValueError('Display PL ownership changed')
                if stimulus and (stimulus.active or stimulus.pending):stimulus.stop()
                if not runtime_paused:
                    unified.controller._stop(now,'runtime_check_pending')
                    unified.controller.selection.clear_pending();unified.controller._clear_mi()
                    runtime_paused=True
                command=commands.poll() if commands else {}
                if command.get('action')=='stop':report['controlled_stop']=True;break
                if command.get('action') in ('force_stop','home'):
                    unified.controller._enter('home',now)
                    command_receipt=dict(id=command['id'],action=command['action'],state='applied',reason='方向已停止')
                snapshot=unified.controller.snapshot(now)
                snapshot.update(mode='runtime_check_pending',direction_armed=False,
                                stimulus_enabled=False,physical_output_enabled=False)
                status(state='waiting_runtime',system=snapshot,runtime_guard=watch.snapshot(),
                       command_receipt=command_receipt,error='运行检查暂未返回，方向已暂停；等待恢复')
                write_json(page_path,dict(page='home',tasks={},updated_monotonic=now,
                                         physical_output_enabled=False,mode='runtime_check_pending'))
                time.sleep(.05);continue
            if runtime_paused:
                unified.controller.selection.clear_pending();unified.controller._stop(now,'runtime_check_recovered')
                unified.buffer_pages.clear();menu_page=-1;runtime_paused=False
                current_status['error']=''
            if buttons:
                actions=buttons.poll(now)
                if actions and vision and vision.active:
                    vision.leave();unified.controller._enter('home',now);unified.buffer_pages.clear()
                if 'pause' in actions:stop_eye(now)
                elif 'start' in actions:start_eye(now)
            if vision:
                if vision.poll_key(now,allow=vision.active or can_enter(live_eye)):
                    if device_link:device_link.stop('图像处理模式')
                    if stimulus and (stimulus.active or stimulus.pending):stimulus.stop()
                    unified.controller._stop(now,'vision_mode')
                    unified.controller.selection.clear_pending()
                    unified.controller.selection.selected=-1
                if vision.active:
                    command=commands.poll() if commands else {}
                    action=command.get('action')
                    if action=='stop':report['controlled_stop']=True;break
                    if action in ('home','force_stop','eye_start','eye_stop'):
                        vision.leave();unified.controller._enter('home',now)
                        unified.buffer_pages.clear()
                        if action=='eye_start':start_eye(now)
                        elif action=='eye_stop':stop_eye(now)
                        continue
                    # Observe native eye events without allowing gaze to select a
                    # hidden control page. Its calibration model stays intact.
                    if live_eye:observe_eye(live_eye,unified.controller,now)
                    if audio:audio.service(unified.controller,blocked=True)
                    if not watch.ready():time.sleep(.02);continue
                    active=lib.display_index()
                    if active>2:raise ValueError('Invalid active framebuffer')
                    target=(active+1)%3
                    vision.compose(buffers[target],now)
                    present_frame(lib,target,require=watch.require)
                    presented+=1
                    if now-last_status>=.5:
                        status(state='vision',frame=presented,system=unified.controller.snapshot(now),
                            vision=vision.snapshot(now),audio_output=False)
                        write_json(page_path,dict(page='home',tasks={},updated_monotonic=now,
                            physical_output_enabled=False,mode='vision'))
                        last_status=now
                    time.sleep(.05);continue
            if unified:
                unified.advance(now-start,now)
                if live:
                    brain_view=brain.apply(unified.controller,now) if brain else {'state':'not_tested','connected':False}
                    now=time.monotonic()
                    if live_eye:
                        live_eye_view=live_eye.poll(unified.controller,now);eye_view=live_eye.snapshot(now)
                    if device_link:
                        service_eye(device_link,unified.controller,live_eye,time.monotonic(),blocked=paused)
                    if selected_index!=unified.controller.video_index:
                        source.close();selected_index=unified.controller.video_index
                        source=BoundedChunks(library.videos[selected_index]['cache'],loop=True)
                        if (source.meta['width'],source.meta['height'])!=(288,512):raise ValueError('Unexpected live cache')
                        block=None;local_index=0;video_eof=False;due=time.monotonic()
                        frame_period=1/source.meta['fps'];unified.buffer_pages.clear()
                        audio_video_frames=0
                    for event in list(unified.controller.events):
                        token=(event['monotonic'],event['action'])
                        if event['action']=='用户视频评价' and token!=last_rating_event:
                            if last_rating_event is None or event['monotonic']>last_rating_event[0]:
                                rating_writer.submit(library.videos[event['index']]['id'],event['rating'])
                                last_rating_event=token
                    if (not (stimulus and stimulus.active) and (now-last_status>=.5
                            or unified.frequency_state!=unified.controller.selected_frequency
                            or unified.overlay_key is None or unified.overlay_key[0]!=unified.controller.page)):
                        unified.refresh_labels(brain_view,eye_view,library.videos[selected_index]['name'],
                                               audio=audio.snapshot() if audio else None)
                calibrating=live_eye is not None and live_eye.guide.phase!='selection'
                video_page=unified.controller.page=='video' and not calibrating
                if video_page and not video_eof and video_started is None:video_started=now
                elif not video_page and video_started is not None:
                    video_elapsed+=now-video_started;video_started=None
                if audio:
                    audio.service(unified.controller,library.videos[selected_index]['id'],
                        max(0,audio_video_frames-1)*frame_period,
                        video_running=video_page and not paused and not video_eof and audio_video_frames>0,
                        blocked=paused or calibrating or bool(stimulus and (stimulus.active or stimulus.pending)))
            if now-last_check>=1:
                if watch:
                    if not watch.ready():continue
                else:
                    if PL.bitfile_name!=display:raise ValueError('Display PL ownership changed')
                    guard.check_runtime()
                last_check=now
            if unified:
                if not watch.ready():continue
                if now-last_status>=.5:
                    status_started=time.monotonic()
                    write_json(page_path,unified.lease(time.monotonic()))
                    snapshot=unified.controller.snapshot(now)
                    if command_receipt and command_receipt.get('state')=='preparing' and stimulus and not stimulus.pending:
                        command_receipt.update(state='applied' if stimulus.active and not stimulus.error else 'rejected',
                            reason='四角已启动' if stimulus.active and not stimulus.error else (stimulus.error or '录制准备已取消'))
                    if live:snapshot.update(mode='live_readonly_hdmi',live_eeg_connected=brain_view.get('state')=='live',
                        brain_api_connected=brain_view.get('connected',False),
                        primary_monitoring_always_enabled=True,optional_task_schedule='page_lease',
                        live_gaze_connected=eye_view.get('connected',False),brain=brain_view,eye=eye_view,
                        video_id=library.videos[selected_index]['id'],video_name=library.videos[selected_index]['name'],
                        mi_exit_enabled=False,stimulus_enabled=bool(stimulus and stimulus.active),eye_only=eye_only,
                        hdmi_fixed_brightness_diagnostic=state.get('hdmi_fixed_brightness_diagnostic') is True,
                        hdmi_stimulus=stimulus.snapshot() if stimulus else {'active':False})
                    status(state='playing' if video_page else 'menu',frame=presented,
                           silent=audio is None,audio_output=audio is not None,
                           audio=audio.snapshot() if audio else None,
                           user_controlled=state.get('user_controlled') is True,
                           command_receipt=command_receipt,
                           system=snapshot,page=unified.controller.page,
                           task_schedule=unified.tasks_for(unified.controller.page),runtime_guard=watch.snapshot())
                    status_io_ms.append((time.monotonic()-status_started)*1000)
                    last_status=now
            command_path=Path('/dev/shm')/(BASE.name+'-player-command.json') if live else BASE/'player_command.json'
            command_started=time.monotonic()
            command=commands.poll() if commands else (json.loads(command_path.read_text()) if command_path.exists() else {})
            # A command can arrive while this iteration renders or publishes status.
            now=time.monotonic()
            if unified:command_io_ms.append((time.monotonic()-command_started)*1000)
            if command.get('session_id')==state['session_id'] and command.get('id')!=last_command:
                last_command=command.get('id')
                action=command.get('action')
                if action=='stop':report['controlled_stop']=True;break
                if action=='pause':
                    paused=True
                    if device_link:device_link.stop('显示已暂停')
                if action=='resume':paused=False;due=now
                if action=='volume':
                    if audio is None:raise ValueError('HDMI audio is not enabled in this session')
                    audio.set_volume(command.get('value'))
                if live:
                    value=command.get('value')
                    command_receipt=dict(id=command['id'],action=action,state='applied',reason='已执行',
                                         updated_monotonic=now)
                    if action in ('hdmi_start','arm','choose') and not 0<=now-command['queued_monotonic']<=3:
                        command_receipt.update(state='rejected',reason='指令已过期，请重新操作')
                        continue
                    if action=='force_stop':unified.controller.force_stop(now)
                    elif action=='fatigue_warning' and 'fatigue' in unified.controller.alerts:
                        unified.controller._enter('fatigue_alert',now)
                    elif action=='home':unified.controller._enter('home',now)
                    elif action=='choose':
                        if not unified.controller.choose(value,now):
                            command_receipt.update(state='rejected',reason='页面未就绪或选择被门控拒绝')
                    elif action=='arm' and not eye_only:
                        if not unified.controller.arm_virtual_direction(now):
                            command_receipt.update(state='rejected',reason='方向页未就绪或疲劳警示未解除')
                    elif action=='hdmi_start' and stimulus:
                        try:
                            if live_eye and live_eye.guide.phase!='selection':
                                raise ValueError('Complete or stop eye calibration before HDMI stimulus')
                            gate=hdmi_preflight(unified.controller.snapshot(now),brain_view.get('ssvep_hdmi') or {})
                            if not gate['ready']:raise ValueError(gate['reason'])
                            options=value if isinstance(value,dict) else dict(consent=value is True,record=False)
                            stimulus.prepare(unified.controller.page_id,consent=options.get('consent'),record=options.get('record'))
                            if stimulus.pending:command_receipt.update(state='preparing',reason='正在等待首批原始脑电写入，尚未闪烁')
                        except (OSError,ValueError) as error:
                            report['errors'].append('HDMI start rejected: '+str(error))
                            command_receipt.update(state='rejected',reason=str(error))
                    elif action=='hdmi_stop' and stimulus:
                        stimulus.stop();unified.controller._stop(now,'hdmi_user_stop')
                        menu_page=-1
                    elif action=='ack':
                        if not unified.controller.acknowledge_alert(value,now):
                            command_receipt.update(state='rejected',reason='警示尚不能确认；等待新鲜合格的正常结果')
                    elif action=='eye_start':
                        start_eye(now)
                    elif action=='eye_stop' and live_eye:
                        stop_eye(now)
                    elif action=='video':
                        ids=[v['id'] for v in library.videos]
                        if value not in ids:raise ValueError('Unknown prepared video')
                        unified.controller.video_index=ids.index(value);unified.controller._enter('video',now)
                    elif action=='rate':
                        rating_writer.submit(library.videos[selected_index]['id'],value)
                        unified.controller.rating=value
                    if action in ('home','choose','ack','video','eye_start','eye_stop','force_stop','fatigue_warning'):
                        if stimulus and (stimulus.active or stimulus.pending):
                            stimulus.service(unified.controller,time.monotonic())
                        # Recompute page/video ownership before rendering the next frame.
                        continue
            if eye:
                events=eye.poll()
                for event in events:
                    if event.get('kind') in ('result','error'):report['eye_results'].append(event)
                if eye.done:
                    code=eye.process.returncode
                    eye.close();eye=None
                    report['eye_exit_code']=code
                    if code:report['errors'].append('Eye diagnostic did not complete successfully')
            elif state.get('eye_repeat_diagnostic') and eye_attempts<3 and now-start>=20*eye_attempts:
                eye=Worker(root,220,160,diagnostic=True,locate=True)
                eye.command('locate');eye_attempts+=1
            if paused:
                if stimulus and (stimulus.active or stimulus.pending):
                    stimulus.stop();menu_page=-1
                status(state='paused',frame=presented)
                time.sleep(.1);continue
            if stimulus:
                was_active=stimulus.active
                if live and not calibrating:
                    stimulus.start_on_entry(unified.controller,time.monotonic(),
                        enabled=state.get('auto_hdmi_on_drive') is True,
                        input_ready=((brain_view.get('ssvep_hdmi') or {}).get('input') or {}).get('ready') is True)
                stimulus.service(unified.controller,time.monotonic())
                if was_active and not stimulus.active:menu_page=-1
                if stimulus.active:
                    time.sleep(.005);continue
            if unified and not video_page:
                if calibrating:
                    target=(lib.display_index()+1)%3
                    view=live_eye_view
                    if view!=unified.calibration_view:
                        buffers[target][:]=unified.renderer.render(view);buffers[target].flush();present_frame(lib,target)
                        live_eye.presented(view,time.monotonic());unified.calibration_view=view
                        unified.buffer_pages.clear();menu_page=-1
                elif menu_page!=(unified.presentation_key(now) if live else unified.controller.page_id):
                    active=lib.display_index();target=(active+1)%3
                    rendered_key=unified.presentation_key(now) if live else unified.controller.page_id
                    unified.compose(buffers[target],target,now=now)
                    if not lib.display_park(target) or lib.display_index()!=target:
                        raise ValueError('Menu frame did not latch')
                    unified.controller.presented(unified.controller.page_id,time.monotonic())
                    menu_page=rendered_key
                if lib.display_status()&0x80000ff1:raise ValueError('Menu display DMA error/halt')
                due=time.monotonic();time.sleep(.025);continue
            if block is None:
                before=time.monotonic()
                try:block=source.acquire(timeout=.05)
                except TimeoutError:
                    buffering+=1;status(state='buffering',frame=presented)
                    due=time.monotonic();continue
                max_wait=max(max_wait,time.monotonic()-before)
                if block is None:
                    if live:
                        # Replay the finite 10fps SD clip at its actual source rate; never count scan repeats.
                        source.close();source=BoundedChunks(library.videos[selected_index]['cache'])
                        audio_video_frames=0
                        block=None;local_index=0;due=time.monotonic();continue
                    if unified:
                        video_eof=True
                        if video_started is not None:
                            video_elapsed+=time.monotonic()-video_started;video_started=None
                        time.sleep(.025);continue
                    break
                local_index=0
            else:
                if presented==0:local_index=0
            slot,n=block
            frame=source.slots[slot][local_index]
            active=lib.display_index()
            if active>2:raise ValueError('Invalid active framebuffer')
            target=(active+1)%3
            copy_started=time.monotonic()
            if unified:
                unified.compose(buffers[target],target,frame)
            elif expander:
                if expander.expand_bgr_360(frame.ctypes.data,buffers[target].ctypes.data,3840)!=1:
                    raise ValueError('Preview expansion failed')
            elif source.meta['format'] in ('gl-bgr24-lz4-v1','gl-bgr24-xor-lz4-v1'):
                np.copyto(buffers[target],frame.reshape((720,1280,3)))
            elif libvideo.bgr_convert(convert,frame.ctypes.data,buffers[target].ctypes.data,3840)!=1:
                raise ValueError('Cache color conversion failed')
            if not unified:buffers[target].flush()
            copied=time.monotonic()
            if unified:
                present_stats=present_frame(lib,target,not_before=due,require=watch.require)
            else:
                delay=due-time.monotonic()
                if delay>0:time.sleep(delay)
                if not lib.display_park(target) or lib.display_index()!=target:
                    raise ValueError('Video frame did not latch')
                before=time.monotonic();counter=lib.display_frames()
                while lib.display_frames()==counter:
                    if time.monotonic()-before>.1:raise ValueError('Display scan stalled')
                    time.sleep(.001)
                if lib.display_status()&0x80000ff1:raise ValueError('Display DMA error/halt')
            if unified:
                unified.controller.presented(unified.controller.page_id,time.monotonic())
                stage_times.append(dict(copy_flush_ms=(copied-copy_started)*1000,**present_stats))
            presented+=1;local_index+=1
            if audio:audio_video_frames=audio_video_frames%source.meta['frames']+1
            frame_time=video_elapsed+time.monotonic()-video_started if unified else time.monotonic()-start
            report.setdefault('first_video_frame_delay_s',frame_time)
            report['new_frame_times'].append(frame_time)
            due+=frame_period
            if time.monotonic()-due>frame_period:
                # Do not race through old frames to inflate average FPS.
                due=time.monotonic()
            if local_index==n:
                source.release(slot);block=None
            if not unified and time.monotonic()-last_status>=.5:
                status(state='playing',frame=presented,frames_total=source.meta['frames'],
                    seconds=presented*frame_period,buffering_events=buffering,
                    ram_cache_mib=source.allocated_bytes/1024**2)
                last_status=time.monotonic()
        if vision:vision.close();vision=None
        elapsed=time.monotonic()-start
        measured=video_elapsed+(time.monotonic()-video_started if video_started else 0.) if unified else elapsed
        times=report['new_frame_times']
        history_complete=times.discarded==0
        sample_start=0 if history_complete or not times else math.ceil(times[0])
        buckets=[sum(s<=t<s+1 for t in times) for s in range(sample_start,int(measured))]
        report.update(performance_history_complete=history_complete,
            performance_sample_start_s=sample_start,discarded_video_samples=times.discarded)
        report.update(frames=presented,wall_s=elapsed,video_active_s=measured,fps=presented/measured if measured else 0.,
            one_second_new_frames=buckets,minimum_full_second_frames=min(buckets) if buckets else None,
            cache_ram_mib=source.allocated_bytes/1024**2,buffering_events=buffering,max_block_wait_s=max_wait,
            cpu_percent=(time.process_time()-cpu)/elapsed*100,
            scan_delta=(lib.display_frames()-scans)&0xffffffff,
            source_fixture=source.meta.get('repeated_fixture_not_new_long_recording',False))
        report['eye_attempts']=eye_attempts
        report['effective_video_dimensions']=[source.meta.get('effective_video_width',source.meta['width']),
                                              source.meta.get('effective_video_height',source.meta['height'])]
        report['meets_16fps']=history_complete and bool(buckets) and min(buckets)>=16 and report['fps']>=16
        first=times[0] if times else 0.
        steady=[sum(first+s<=t<first+s+1 for t in times) for s in range(int(measured-first))]
        report.update(steady_one_second_new_frames=steady,
                      steady_meets_16fps=history_complete and bool(steady) and min(steady)>=16,
                      playback_loop_of_finite_source=live)
        report['eof_reached']=presented==source.meta['frames']
        if live:report.update(brain=brain_view,eye=eye_view,source_fps=source.meta['fps'],
            video_id=library.videos[selected_index]['id'],ratings_persisted=library.path.exists(),
            mi_exit_enabled=False,stimulus_enabled=bool(stimulus and stimulus.active),eye_only=eye_only,
            hdmi_stimulus=stimulus.snapshot() if stimulus else {'active':False},
            system=unified.controller.snapshot(time.monotonic()))
        if unified:
            report.update(page_transitions=unified.transitions,display_overlay_loads=1,
                video_roi=list(unified.roi),frame_stage_times=stage_times,
                status_io_ms=status_io_ms,command_io_ms=command_io_ms,
                status_storage='volatile_ram_with_final_disk_snapshot',
                task_schedule=unified.tasks_for(unified.controller.page))
    except KeyboardInterrupt:report['controlled_stop']=True
    except Exception as error:report['errors'].append(str(error))
    finally:
        if device_link:
            device_link.close()
            report.update(eye_device_control_configured=True,devices=device_link.snapshot(),
                          physical_control=device_link.snapshot()['ever_enabled'])
        if vision:
            try:vision.close();vision=None
            except Exception as exc:
                report['errors'].append('Vision cleanup: '+str(exc))
                if vision.worker and vision.worker.thread.is_alive():
                    report['buffer_ownership_retained']=True
                    write_json(BASE/(state['session_id']+'-report.json'),report)
                    status(state='error',error='Vision worker stuck; independent recovery required',original_restored=False)
                    signal.signal(signal.SIGTERM,signal.SIG_IGN)
                    while True:time.sleep(1)
        if audio:
            try:audio.close()
            except RuntimeError as error:
                report['errors'].append('Audio cleanup: '+str(error))
                write_json(BASE/(state['session_id']+'-report.json'),report)
                status(state='error',error='Audio has not stopped; retain PL until recovery',original_restored=False)
                signal.signal(signal.SIGTERM,signal.SIG_IGN)
                while True:time.sleep(1)
        if stimulus:
            # Never hand the DMA buffers back until the scan writer has stopped.
            try:stimulus.close()
            except RuntimeError as error:
                report['errors'].append('Stimulus cleanup: '+str(error))
                report['buffer_ownership_retained']=True
                write_json(BASE/(state['session_id']+'-report.json'),report)
                status(state='error',error='Stimulus worker stuck; independent recovery required',
                       original_restored=False)
                signal.signal(signal.SIGTERM,signal.SIG_IGN)
                while True:time.sleep(1)
        if buttons:buttons.close()
        for name,component in (('brain',brain),('live_eye',live_eye),('rating_writer',rating_writer)):
            if component:
                try:component.close()
                except Exception as error:report['errors'].append(name+' cleanup: '+str(error))
        if watch:
            report['runtime_guard_final']=watch.snapshot()
            try:watch.close()
            except Exception as error:report['errors'].append('Runtime watch cleanup: '+str(error))
            report['runtime_check_ms']=watch.check_ms
        if unified:
            closed_lease=dict(page='home',updated_monotonic=0.,mode='scripted_hdmi_replay',
                              physical_output_enabled=False,reason='display_session_closed')
            write_json(page_path,closed_lease)
            if page_path!=BASE/'system_page.json':write_json(BASE/'system_page.json',closed_lease)
            if live:
                # A clean close restores independent SSVEP tests. A crash leaves
                # an expired lease, which keeps the optional lane fail-closed.
                page_path.unlink(missing_ok=True)
        if eye:
            try:eye.close();report['eye_cleanup_done']=True
            except Exception as error:report['errors'].append('Eye cleanup: '+str(error))
        if source:
            try:source.close()
            except Exception as error:report['errors'].append('Cache cleanup: '+str(error))
        if convert:
            try:libvideo.bgr_close(convert)
            except Exception as error:report['errors'].append('Converter cleanup: '+str(error))
        with open(BASE/'restore.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            try:
                halted=bool(lib.display_close()) if mapped else True
                report['display_halted']=halted
                def restore():
                    if hashlib.sha256(Path(original).read_bytes()).hexdigest()!=state['hardware_hashes'][original]:
                        raise ValueError('Recovery bit changed')
                    Overlay(original)
                    if PL.bitfile_name!=original:raise ValueError('Recovery did not verify')
                    report['original_restored']=True
                if not halted:restore()
                for buffer in buffers:buffer.freebuffer()
                report['buffers_released']=True
                if attempted and not report['original_restored']:restore()
                if not attempted:report['original_restored']=PL.bitfile_name==original
            except Exception as error:report['errors'].append('Recovery: '+str(error))
        if vision:
            try:
                if not report['original_restored']:raise RuntimeError('Recovery overlay has not verified')
                vision.close(pl_reset=True);vision=None
            except Exception as exc:
                report['errors'].append('Vision retained: '+str(exc))
                report['buffer_ownership_retained']=True
                write_json(BASE/(state['session_id']+'-report.json'),report)
                status(state='error',error='Vision buffers retained; independent recovery required',original_restored=report['original_restored'])
                signal.signal(signal.SIGTERM,signal.SIG_IGN)
                while True:time.sleep(1)
        report['peak_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
        write_json(BASE/(state['session_id']+'-report.json'),report)
        status(state='stopped' if report.get('controlled_stop') else 'complete' if not report['errors'] else 'error',
            frame=report.get('frames',0),seconds=report.get('video_active_s',0),system=None,
            original_restored=report['original_restored'],error='; '.join(report['errors']))
        if status_path!=BASE/'player_status.json':write_json(BASE/'player_status.json',current_status)
        if not report['buffers_released']:
            signal.signal(signal.SIGTERM,signal.SIG_IGN)
            while True:time.sleep(1)
        for lock in locks:lock.close()
    if report['errors']:raise SystemExit(1)


if __name__=='__main__':main()
