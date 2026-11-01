"""HDMI guidance session. Defaults to a ready page, never starts human sampling."""
import argparse
from contextlib import ExitStack
import ctypes as C
import fcntl
import json
from pathlib import Path
import signal
import time
from dataclasses import replace
from guide import Guide, POINTS, HORIZONTAL_POINTS, FIVE_POINTS, DIRECTION_POINTS
from calibration_worker import Worker, CalibrationRestart
from guide_render import Renderer
from buttons import Buttons
from tracking import Tracking
from validation import Validation, TARGETS
from selection import Selection
from media_menu import Catalog, MediaMenu
from accuracy_audit import AccuracyAudit

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=900)
    parser.add_argument("--control-dir", default="/dev/shm/tobii_z15/guide")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--no-buttons", action="store_true")
    parser.add_argument("--live",action="store_true")
    parser.add_argument("--relaxed",action="store_true",help="Longer settle and bounded same-point retries")
    parser.add_argument("--selection-test",action="store_true",help="Calibrate then keep streaming to a three-region dwell test")
    parser.add_argument("--relative-selection",action="store_true",help="Board-only three horizontal anchors from available live gaze; no OEM model compute")
    parser.add_argument("--accuracy-test", action="store_true", help="After relative calibration, observe 30 independent cued choices; no actuators")
    parser.add_argument("--local-media", action="store_true", help="Relative gaze menus with SD-card speech, silent video and music")
    parser.add_argument("--media-dir", type=Path, help="Directory containing playlist.json and prepared assets")
    parser.add_argument("--audio-device", help="ALSA device override, e.g. plughw:CARD=Device,DEV=0")
    parser.add_argument("--calibration-points",type=int,choices=(3,5,9),default=3)
    parser.add_argument("--width-mm",type=float,default=220)
    parser.add_argument("--height-mm",type=float,default=160)
    parser.add_argument("--validation-model",type=Path,help="Verify directions using this retained personal calibration")
    parser.add_argument("--coexist", action="store_true", help="Audited ARM brain coexistence; never stop brain services")
    parser.add_argument("--coexist-seconds", type=int, help="Finite coexistence acceptance run, including local-media mode")
    parser.add_argument("--coexist-locate", action="store_true", help="Start the existing non-calibrating positioning check")
    parser.add_argument("--shared-pl", action="store_true", help="Borrow the already-loaded eye PL from the acceptance owner")
    args = parser.parse_args()
    if args.local_media:
        args.live = args.relative_selection = True
        args.seconds = 0
    if args.coexist_seconds is not None:
        if not args.coexist or not 1 <= args.coexist_seconds <= 900:
            raise ValueError("Finite coexistence run must be between 1 and 900 seconds")
        args.seconds = args.coexist_seconds
    if args.coexist_locate and (not args.coexist or not args.live or args.preview):
        raise ValueError("Positioning check requires explicit live coexistence mode")
    if args.shared_pl and not args.coexist:
        raise ValueError("Shared PL requires coexistence mode")
    if args.relative_selection:args.selection_test=True;args.calibration_points=3
    if args.accuracy_test and (not args.relative_selection or args.local_media):
        raise ValueError("Accuracy test requires relative selection without media actions")
    if args.selection_test:
        if not args.live or args.validation_model or args.preview:
            raise ValueError("Selection test requires live calibration, without restored model or preview")
        args.relaxed=True
    from pynq import Overlay, PL, allocate
    import numpy as np
    root = Path(__file__).resolve().parents[1]
    control = Path(args.control_dir)
    control.mkdir(parents=True, exist_ok=True)
    accuracy = AccuracyAudit(control / "accuracy.json") if args.accuracy_test else None
    lock = open("/run/lock/tobii_display.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    # Only the owner may clear stale commands; a rejected second instance must
    # not disturb the running eye session.
    for name in ("command.json", "backend.json"):
        (control/name).unlink(missing_ok=True)
    original = PL.bitfile_name
    if not original or not Path(original).exists():
        raise RuntimeError("Original overlay unavailable")
    coexist, pl_lock = None, None
    if args.coexist:
        from coexist_guard import CoexistGuard
        if not args.shared_pl:
            pl_lock = open("/run/lock/guardianloop-pl.lock", "a")
            fcntl.flock(pl_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        coexist = CoexistGuard(root, original, shared=args.shared_pl)
        print("coexist_admission=" + json.dumps(coexist.verify()), flush=True)
    lib = C.CDLL(str(root/"libtobii_display.so"))
    lib.display_open.argtypes = [C.POINTER(C.c_uint32)]
    lib.display_park.argtypes = [C.c_uint]
    lib.display_status.restype = lib.display_frames.restype = C.c_uint32
    buffers, overlay, mapped, download_attempted = [], None, False, False
    validating=args.validation_model is not None
    if validating and (not args.live or not args.validation_model.is_absolute() or not args.validation_model.is_file()):
        raise ValueError("Validation requires live mode and an existing absolute model path")
    points = DIRECTION_POINTS if args.relative_selection else {3:HORIZONTAL_POINTS,5:FIVE_POINTS,9:POINTS}[args.calibration_points] if args.selection_test else POINTS
    state = Validation() if validating else Guide(relaxed=args.relaxed,points=points,diagnostic_seconds=10 if args.selection_test else 15,collect_seconds=6 if args.relative_selection else 3)
    renderer = Renderer(buttons=not args.no_buttons,live=args.live,relaxed=args.relaxed,validation=validating,selection_test=args.selection_test,calibration_points=args.calibration_points,relative=args.relative_selection,local_media=args.local_media,accuracy_test=args.accuracy_test)
    selection=None
    menu = None
    catalog = Catalog(args.media_dir or root / "media") if args.local_media else None
    buttons = None
    worker, sent_point, compute_sent = None, -1, False
    restart = CalibrationRestart()
    cleanup_pending = None
    tracking = Tracking(reference_cm=(40,43) if args.relative_selection else None)
    generation, last_command, last_backend, last_view = None, None, None, None
    def begin(now,preview,diagnostic=False):
        nonlocal worker,sent_point,compute_sent,generation,cleanup_pending,tracking,menu,selection
        if state.phase not in ("ready","complete","failed","cancelled","checked","validated","usable","validation_failed","restarting"):
            return False
        if worker is not None:
            if worker.process.poll() is None:
                state.detail="上一轮采样仍在停止，请稍后再按 PS_KEY0"
                return False
            worker.close();worker=None
        if menu is not None:
            menu.close();menu=None
        selection=None
        generation="session-%.6f"%now
        sent_point,compute_sent=-1,False
        cleanup_pending=None
        tracking=Tracking(reference_cm=(40,43) if args.relative_selection else None)
        if preview:
            state.start(now,preview=True)
        else:
            worker=Worker(root,args.width_mm,args.height_mm,relaxed=args.relaxed,diagnostic=diagnostic,validation_model=args.validation_model,selection_test=args.selection_test and not diagnostic,locate=args.selection_test and diagnostic,calibration_points=args.calibration_points,relative=args.relative_selection and not diagnostic)
            state.phase="diagnostic" if diagnostic else "connecting"
            state.started=now
            state.preview=False
            state.detail=""
            print("real_session="+str(worker.directory),flush=True)
        return True
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGINT,stop)
    signal.signal(signal.SIGTERM,stop)
    try:
        if not args.no_buttons:
            buttons=Buttons()
            print("buttons=PS_KEY0:%s PS_KEY1:pause"%("start_validation" if validating else "start_calibration" if args.live else "start_preview"),flush=True)
        download_attempted = not args.shared_pl
        overlay = Overlay(str(root/"overlay/eye_wifi.bit"), download=not args.shared_pl)
        for name,address in {"axi_vdma_0":0x43000000,"axi_vdma_1":0x43010000,
                             "live_osd_0":0x43c00000,"v_tc_0":0x43c10000}.items():
            if overlay.ip_dict.get(name,{}).get("phys_addr") != address:
                raise RuntimeError("Overlay mismatch: "+name)
        initial = renderer.render(state.tick(time.monotonic()))
        for _ in range(3):
            b=allocate(shape=initial.shape,dtype=np.uint8)
            buffers.append(b)
            b[:]=initial
            b.flush()
        mapped = True
        physical=(C.c_uint32*3)(*[b.physical_address for b in buffers])
        if not lib.display_open(physical) or not lib.display_park(0):
            raise RuntimeError("HDMI initialization failed")
        current=0
        if args.coexist_locate:
            begin(time.monotonic(), preview=False, diagnostic=True)
        if args.preview:
            state.start(time.monotonic(),preview=True)
        deadline=time.monotonic()+args.seconds if args.seconds>0 else float("inf")
        count,progress_time,last_log=lib.display_frames(),time.monotonic(),0
        last_coexist_check = 0
        while time.monotonic()<deadline:
            now=time.monotonic()
            if coexist is not None and now-last_coexist_check >= 1:
                if PL.bitfile_name != str(root/"overlay/eye_wifi.bit"):
                    raise RuntimeError("PL owner changed during coexistence")
                coexist.check_runtime()
                last_coexist_check = now
            if menu is not None and state.phase!="selection":
                menu.close();menu=None;selection=None
            if buttons is not None:
                actions=buttons.poll(now)
                # Cancel has priority if both keys are pressed together.
                if "pause" in actions:
                    restart.cancel()
                    if accuracy is not None:accuracy.cancel("pause")
                    if selection is not None and state.phase=="selection":
                        if menu is not None:menu.pause(now)
                        else:selection.toggle_pause()
                    else:
                        state.cancel()
                        if worker is not None:worker.abort()
                    print("button=PS_KEY1 action=pause",flush=True)
                elif "start" in actions:
                    if state.phase=="positioning":
                        state.start(now,preview=False)
                        print("button=PS_KEY0 action=confirm_position",flush=True)
                    elif accuracy is not None and state.phase=="selection":
                        accuracy.start()
                        print("button=PS_KEY0 action=accuracy_start",flush=True)
                    elif args.relative_selection and restart.request(state,worker,menu,selection,now):
                        menu=None;selection=None
                        print("button=PS_KEY0 action=recalibrate",flush=True)
                    elif state.phase in ("ready","complete","failed","cancelled","checked","validated","usable","validation_failed"):
                        if begin(now,preview=not args.live):
                            print("button=PS_KEY0 action=%s"%("start_validation" if validating else "start_calibration" if args.live else "start_preview"),flush=True)
                    else:
                        print("button=PS_KEY0 action=ignored_running",flush=True)
            try:
                command=json.loads((control/"command.json").read_text())
            except (FileNotFoundError,json.JSONDecodeError):
                command={}
            ident=command.get("id")
            if ident is not None and ident!=last_command:
                last_command=ident
                action=command.get("action")
                if action=="pause":
                    restart.cancel()
                    if accuracy is not None:accuracy.cancel("pause")
                    if selection is not None and state.phase=="selection":
                        if menu is not None:menu.pause(now)
                        else:selection.toggle_pause()
                    else:
                        state.cancel()
                        if worker is not None:worker.abort()
                elif action=="preview" and not validating:
                    if state.phase in ("ready","complete","failed","cancelled","checked"):
                        begin(now,preview=True)
                elif action=="start":
                    if state.phase=="positioning":
                        state.start(now,preview=False)
                        print("command action=confirm_position",flush=True)
                    elif accuracy is not None and state.phase=="selection":
                        accuracy.start()
                        print("command action=accuracy_start",flush=True)
                    elif args.relative_selection and restart.request(state,worker,menu,selection,now):
                        menu=None;selection=None
                        print("command action=recalibrate",flush=True)
                    elif args.live:
                        if not restart.pending:begin(now,preview=False)
                    else:
                        state.phase="failed"
                        state.detail="真实采样未启用，请先完成连接检查"
                elif action=="check" and args.live and not validating and not restart.pending:
                    begin(now,preview=False,diagnostic=True)
            replacement=restart.poll(worker,time.monotonic())
            if replacement=="ready":
                begin(time.monotonic(),preview=False)
            elif replacement=="timeout":
                state.phase="failed"
                state.detail="上一轮采样超过 12 秒未退出；请退出程序后重新启动"
            if worker is not None:
                for event in worker.poll():
                    if restart.pending:
                        continue  # Old points/results/exit errors cannot mutate the new session.
                    if event.get("kind") not in ("quality","gaze","direction_gaze","horizontal_gaze"):print("worker_event="+json.dumps(event),flush=True)
                    if event.get("kind")=="ready" and state.phase=="connecting":
                        if args.relative_selection:
                            state.phase="positioning"
                        else:
                            state.phase="ready"
                            state.start(time.monotonic(),preview=False)
                    elif event.get("kind")=="point":
                        state.response(event.get("point"),event.get("accepted") is True)
                        if event.get("accepted") is False and event.get("point")==state.point and state.phase in ("collect","waiting"):
                            state.phase="failed"
                            cleanup_pending=time.monotonic()
                            state.detail="本点可用方向数据不足；已停止，请调整后重做" if args.relative_selection else ("本点采样失败 0x%08X；已停止，请调整后重新校准" if args.selection_test else "本点采样失败 0x%08X；已停止，原校准正在恢复")%event.get("status",0)
                    elif event.get("kind")=="retry" and event.get("point")==state.point and state.phase in ("collect","waiting"):
                        state.detail="正在第 %d / %d 次采样，请继续看白点"%(event["attempt"],event["limit"])
                    elif event.get("kind")=="quality":
                        tracking.update(event,time.monotonic())
                    elif event.get("kind")=="gaze" and validating:
                        state.update_gaze(event,time.monotonic())
                    elif event.get("kind")=="gaze" and selection is not None and state.phase=="selection" and not args.local_media:
                        if selection.update(event,time.monotonic()):
                            print("selection_event="+json.dumps(dict(region=selection.selected,count=selection.confirmations,monotonic_ns=event.get("monotonic_ns"))),flush=True)
                    elif event.get("kind")=="horizontal_gaze" and args.relative_selection and selection is not None and state.phase=="selection":
                        if menu is not None:
                            if menu.gaze(event,time.monotonic()):
                                print("media_selection="+json.dumps(dict(action=menu.last_action,region=selection.selected,count=selection.confirmations,monotonic_ns=event.get("monotonic_ns"))),flush=True)
                        elif not args.local_media and selection.update_horizontal(event,time.monotonic()):
                            if accuracy is not None:accuracy.observe(selection.selected,event,time.monotonic())
                            print("selection_event="+json.dumps(dict(region=selection.selected,count=selection.confirmations,monotonic_ns=event.get("monotonic_ns"),mode="relative")),flush=True)
                    elif event.get("kind")=="direction_ready" and args.relative_selection and state.phase=="compute":
                        if event.get("trained") is True:
                            selection=Selection();state.phase="selection"
                        else:state.phase="failed";state.detail="三个方向未分开，请调整位置后重新标定"
                    elif event.get("kind")=="calibration_ready" and args.selection_test and state.phase=="compute":
                        state.result(event.get("calibrated") is True,event.get("valid_samples"))
                        if state.phase=="complete":
                            selection=Selection()
                            state.phase="selection"
                    elif event.get("kind")=="stage" and state.phase=="diagnostic":
                        state.detail={"baseline":"普通采集", "calibration_mode":"校准模式中", "after_exit":"退出校准后", "locate":"只检查双眼定位，约 10 秒"}.get(event.get("stage"),"正在核对")
                        if event.get("stage")=="locate":state.started=time.monotonic()
                    elif event.get("kind")=="rollback" and state.phase in ("failed","cancelled"):
                        state.detail="采样已停止，原校准已恢复并核对" if event.get("verified") is True else "采样已停止，原校准恢复未能核对"
                    elif event.get("kind")=="result":
                        if validating:state.finish(event)
                        elif state.phase=="diagnostic" and event.get("diagnostic") is True:
                            if event.get("located") is True:
                                state.phase="checked"
                                state.detail="定位检查结束：双眼同时检出 %d / %d 帧；本轮没有校准"%(event.get("both",0),event.get("samples",0))
                            else:
                                state.phase="checked" if event.get("unchanged") is True else "failed"
                                state.detail="三段采集检查结束，原校准读回一致；本轮没有个人校准" if event.get("unchanged") is True else "原校准核对失败"
                        else:state.result(event.get("calibrated") is True,event.get("valid_samples"))
                    elif event.get("kind")=="error" and state.phase not in ("cancelled","failed"):
                        computing=state.phase=="compute"
                        positioning=state.phase=="positioning"
                        state.phase="failed"
                        state.detail="位置检查采样已结束，按 PS_KEY0 可重新连接" if positioning else "三个方向数据不足或未分开，请调整后重做" if args.relative_selection else ("%d 点采样完成，校准计算失败 0x%08X；请重新校准"%(len(points),event.get("status",0)) if computing and args.selection_test else "模组处理未完成，错误 %s；可以移开视线"%event.get("code"))
                if state.phase=="connecting" and now-worker.started>(20 if validating else 12):
                    state.phase="failed";state.detail="连接等待超过 12 秒，请检查 USB"
                if state.phase=="diagnostic" and now-state.started>30:
                    state.phase="failed";state.detail="定位检查等待超过 30 秒，正在停止"
            try:
                backend=json.loads((control/"backend.json").read_text())
            except (FileNotFoundError,json.JSONDecodeError):
                backend={}
            event=backend.get("event_id")
            if (not validating and event is not None and event!=last_backend and
                backend.get("generation")==generation and not state.preview and worker is None):
                last_backend=event
                if backend.get("kind")=="point":
                    state.response(backend.get("point"),backend.get("accepted") is True)
                elif backend.get("kind")=="result":
                    state.result(backend.get("calibrated") is True,backend.get("valid_samples"))
            now=time.monotonic()
            if args.local_media and menu is None and selection is not None and state.phase=="selection":
                menu=MediaMenu(catalog,selection,now=now,audio_device=args.audio_device)
            if menu is not None:menu.tick(now)
            if accuracy is not None and state.phase in ("failed", "cancelled", "restarting"):
                accuracy.cancel("eye_phase_" + state.phase)
            view=state.tick(now)
            if state.phase=="selection" and selection is not None:
                view=menu.view(now) if menu is not None else selection.view(now)
                if accuracy is not None:view=accuracy.view(view,now)
            if worker is not None and view.phase in ("positioning","prepare","settle","collect","waiting","compute","diagnostic","vsettle","vcollect","selection","menu","video","failed","cancelled","checked") and not view.preview:
                view=replace(view,tracking=tracking.lines(now))
            # Acknowledge presentation only after parking has selected the new
            # flushed buffer. Never write into the displayed CMA frame.
            if view!=last_view:
                previous_view=last_view
                next_index=(current+1)%3
                renderer.render_into(buffers[next_index], view)
                buffers[next_index].flush()
                if not lib.display_park(next_index):
                    raise RuntimeError("HDMI frame switch failed")
                current,last_view=next_index,view
                if accuracy is not None:accuracy.presented(view,time.monotonic())
                if menu is not None:menu.presented(time.monotonic())
                payload=dict(phase=view.phase,point=view.point,remaining=view.remaining,
                             preview=view.preview,generation=generation,monotonic_s=now)
                if view.tracking:payload["tracking"]=view.tracking
                if view.phase=="selection":
                    payload.update(hover=view.hover,selected=view.selected,progress=view.progress,confirmations=view.confirmations,paused=view.paused)
                elif view.phase in ("menu","video"):
                    payload.update(page=menu.page,page_id=view.page_id,reading=view.reading,
                                   hover=view.hover,selected=view.selected,progress=view.progress,
                                   confirmations=view.confirmations,paused=view.paused,
                                   video_frame=view.video_frame,audio_status=menu.audio.status)
                part=control/"presented.json.part"
                part.write_text(json.dumps(payload))
                part.replace(control/"presented.json")
                # Actual flushed/parked target precedes every sample command.
                # Refresh the minimum dwell origin after the target is visible.
                if worker is not None and not view.preview:
                    if args.selection_test and view.phase=="diagnostic" and not compute_sent:
                        compute_sent=True
                        state.started=time.monotonic()
                        worker.command("locate")
                    elif validating and view.phase in ("vsettle","vcollect") and (previous_view is None or previous_view.phase!=view.phase or previous_view.point!=view.point):
                        state.started=time.monotonic()
                        if view.phase=='vsettle':worker.command('transition')
                        else:
                            x,y=TARGETS[view.point]
                            worker.command('target %d %.9f %.9f'%(view.point,x,y))
                    elif validating and view.phase=='vprocessing' and not compute_sent:
                        compute_sent=True;state.started=time.monotonic();worker.command('finish')
                    elif view.phase=="settle" and (previous_view is None or previous_view.phase!="settle" or previous_view.point!=view.point):
                        state.started=time.monotonic()
                        state.point_started=state.started
                    if view.phase=="collect" and view.point!=sent_point:
                        sent_point=view.point
                        state.started=time.monotonic()
                        x,y=points[view.point]
                        worker.command("point %d %.9f %.9f"%(view.point,x,y))
                    elif view.phase=="compute" and not compute_sent:
                        compute_sent=True
                        state.started=time.monotonic()
                        worker.command("compute")
            if worker is not None and state.phase in ("failed","cancelled") and (cleanup_pending is None or now-cleanup_pending>10):
                worker.abort()
            next_count,status=lib.display_frames(),lib.display_status()
            if status & 0xff1:
                raise RuntimeError("VDMA fault/halt")
            if next_count!=count:
                count,progress_time=next_count,now
            elif now-progress_time>2:
                raise RuntimeError("HDMI output stalled")
            if now-last_log>=5:
                print("phase=%s hdmi_frames=%d tx_status=%08x"%(view.phase,count,status),flush=True)
                last_log=now
            time.sleep(max(.001,.1-(time.monotonic()-now)) if menu is not None else .1)
    except KeyboardInterrupt:
        print("guide_stopped",flush=True)
    finally:
        with ExitStack() as cleanup:
            if accuracy is not None:cleanup.callback(accuracy.cancel, "session_exit")
            cleanup.callback(lock.close)
            if pl_lock is not None:cleanup.callback(pl_lock.close)
            from coexist_guard import cleanup_display
            cleanup.callback(cleanup_display, lib, overlay, mapped, buffers, original, Overlay,
                             download_attempted=download_attempted, restore=not args.shared_pl)
            if buttons is not None:cleanup.callback(buttons.close)
            if worker is not None:cleanup.callback(worker.close)
            if menu is not None:cleanup.callback(menu.close)

if __name__=="__main__":
    main()
