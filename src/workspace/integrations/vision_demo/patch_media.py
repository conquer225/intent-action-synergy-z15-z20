"""Produce a reviewed media-player candidate; never edits the installed runtime."""
from pathlib import Path


def replace_once(text,old,new):
    if text.count(old)!=1:raise ValueError('Unrecognized media-player anchor: '+old[:70])
    return text.replace(old,new,1)

def patch_audio(text,bit_sha,hwh_sha):
    """Replace the pinned pair together; retain the existing audio hash gate."""
    text=replace_once(text,'ef60c903c519efb7b4eb5dbcadca1594208f5049207e1a92e422b918dbaae2f6',bit_sha)
    return replace_once(text,'e7c3bcb9024393fba331f6b0c9b85b4a488832555c06309142703b308819767d',hwh_sha)


def patch(text):
    # The preloaded video block owns its cursor before any signal/calibration
    # frames are presented. The global display count is not a video-start flag.
    anchor='        block=source.acquire(timeout=10)\n'
    text=replace_once(text,anchor,anchor+'        local_index=0\n')
    text=replace_once(text,'    audio=None;audio_video_frames=0\n',
        '    audio=None;audio_video_frames=0;vision=None\n')
    anchor='            buttons=Buttons()\n'
    text=replace_once(text,anchor,anchor+'''        if live and state.get('vision_demo'):
            from vision_demo.addon import VisionAddon
            from vision_demo.eye_observer import observe_eye,can_enter
            from vision_demo.hdmi_mode import service_vision
            vision=VisionAddon(overlay,state['vision_demo'],
                lambda:live_eye.worker.directory if live_eye and live_eye.worker.process.poll() is None else None)
''')
    anchor='                actions=buttons.poll(now)\n'
    text=replace_once(text,anchor,anchor+'''                if actions and vision and vision.active:
                    vision.leave();unified.controller._enter('home',now);unified.buffer_pages.clear()
''')
    anchor='            if unified:\n                unified.advance(now-start,now)\n'
    block='''            if vision:
                if vision.poll_key(now,allow=vision.active or can_enter(live_eye)):
                    if device_link:device_link.stop('信号或图像演示模式')
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
                    if vision.signal_mode:
                        vision.signal.output_ready=audio is None or audio.session.snapshot().get('pid') is None
                    camera_error=service_vision(vision,unified,now)
                    if camera_error:
                        current_status.update(error='OV5640 启动失败，已返回主界面',
                            vision=dict(active=False,error=camera_error))
                        menu_page=-1
                        continue
                    if not vision.streaming:
                        active=lib.display_index()
                        if active>2:raise ValueError('Invalid active framebuffer')
                        target=(active+1)%3
                        vision.compose(buffers[target],now)
                        present_frame(lib,target,require=watch.require)
                        presented+=1
                    if now-last_status>=.5:
                        status(state='vision',frame=presented,system=unified.controller.snapshot(now),
                            vision=vision.snapshot(now),audio_output=bool(vision.signal_mode and vision.signal and vision.signal.session and vision.signal.session.snapshot().get('phase')=='feeding'))
                        write_json(page_path,dict(page='home',tasks={},updated_monotonic=now,
                            physical_output_enabled=False,mode='vision'))
                        last_status=now
                    time.sleep(.025 if vision.streaming else .005 if vision.signal_mode else .05);continue
'''
    text=replace_once(text,anchor,block+anchor)
    # Stop camera/HLS before display cleanup. If it fails, the original finally
    # still restores PL; keep this as a raised error rather than hiding failure.
    anchor='        elapsed=time.monotonic()-start\n'
    text=replace_once(text,anchor,'        if vision:vision.close();vision=None\n'+anchor)
    # Retain all DMA owners if a worker cannot stop. A stopped worker with a
    # failed DMA halt may release buffers only after verified PL restoration.
    anchor="        if audio:\n            try:audio.close()\n"
    text=replace_once(text,anchor,'''        if vision:
            try:vision.close();vision=None
            except Exception as exc:
                report['errors'].append('Vision cleanup: '+str(exc))
                if (vision.worker and vision.worker.thread.is_alive()) or (vision.signal and vision.signal.analysis and vision.signal.analysis.thread.is_alive()):
                    report['buffer_ownership_retained']=True
                    write_json(BASE/(state['session_id']+'-report.json'),report)
                    status(state='error',error='Vision worker stuck; independent recovery required',original_restored=False)
                    signal.signal(signal.SIGTERM,signal.SIG_IGN)
                    while True:time.sleep(1)
'''+anchor)
    anchor="        report['peak_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024\n"
    text=replace_once(text,anchor,'''        if vision:
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
'''+anchor)
    compile(text,'media_player-vision.py','exec')
    return text


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();a.output.write_text(patch(a.source.read_text(encoding='utf-8')),encoding='utf-8')
