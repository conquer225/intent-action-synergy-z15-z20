"""Shared session for terminal controls, offline preview and one HDMI display."""
import argparse,hashlib,json,math,queue,signal,sys,threading,time
from pathlib import Path
from . import vendor
from .tasks import TaskController
from .menu import Menu
from .simulation import SimulatedPeer,SimulatedAudio
from .monitor import ProcessModel,BrainApi,PendulumConnection
from .telemetry import SignalConnection
from .intents import BrainSelection
ROOT=Path(__file__).resolve().parents[1]

class Session:
    def __init__(self,factory,simulation=False):
        self.menu=Menu(TaskController(factory),'simulation' if simulation else 'live')
        self.simulation=simulation;self.eye=None;self.quit=False;self.model=ProcessModel();self.brain=BrainSelection();self.pipeline=None;self.mi_worker=None;self.mpu_zero_done=False
    def command(self,word,now):
        word=word.strip().lower();m=self.menu
        if word in ('q','quit'):m.tasks.estop();self.quit=True
        elif word.startswith('choose '):
            if not self.simulation:raise RuntimeError('鼠标选区只用于模拟预览')
            index=int(word.split()[1])
            if m.presented_at is None or now-m.presented_at<m.read_seconds:raise RuntimeError('新页面请先阅读再选择')
            if m.ssvep_active:m.brain_choice(index,now)
            else:m.choose(index,now)
        elif word=='mode_next':
            modes=('eye','emg','eeg');m.switch_mode(modes[(modes.index(m.interaction_mode)+1)%3],now)
            if self.eye:self.eye.close();self.eye=None
            self.brain.start(None,now)
        elif word in ('eye','emg','eeg'):
            m.switch_mode(word,now)
            if self.eye:self.eye.close();self.eye=None
            self.brain.start(None,now)
        elif word in ('s','stop','escape','esc'):
            m._stop(now,'已停止，需手动重新启用')
            if m.media:m.media.stop()
            if self.mi_worker:self.mi_worker.stop()
        elif word in ('1','2','3','4','5','6'):
            modes=(('eye','hand'),('eye','pendulum'),('contact','hand'),('mpu','pendulum'),('brain','hand'),('brain','pendulum'))
            m.select(*modes[int(word)-1],now)
            self.mpu_zero_done=False
        elif word in ('e','enable'):
            if m.page not in ('actions','turns','pend_start','emg','mpu'):raise RuntimeError('请先进入当前模式的设备控制页')
            if m.interaction_mode=='emg' and m.page!='mpu' and (not m.tasks.peer or m.tasks.mode!='contact'):m.select('contact','hand',now)
            if not self.simulation and m.tasks.mode=='eye' and (self.eye is None or not self.eye.snapshot(now)['valid']):raise RuntimeError('先完成眼动校准并取得新鲜输入')
            m.tasks.enable();m.message='已启用；停止可随时执行'
        elif word in ('z','zero'):m.tasks.zero();self.mpu_zero_done=True;m.message='MPU参考已设置，保持静止后启用'
        elif word in ('operate','process','technical','devices','auxiliary'):
            if m.interaction_mode=='eye':m.page_to(word,now)
            else:m.page_to({'emg':'emg','eeg':'eeg'}[m.interaction_mode] if word=='operate' else word,now)
        elif word in ('monitor','mi','ssvep'):
            if m.interaction_mode!='eeg':raise RuntimeError('请先切换到脑电模式')
            m.tasks.close();m.page_to({'monitor':'eeg','mi':'mi','ssvep':'ssvep_devices'}[word],now)
        elif word in ('mi-left','mi-right','mi-rest'):
            if m.interaction_mode!='eeg' or m.page!='mi' or not self.mi_worker:raise RuntimeError('先进入运动想象任务并检查板端配置')
            m.tasks.estop();self.mi_worker.start(word.split('-')[1])
        elif word=='pause':
            m.pause(now)
            if self.mi_worker:self.mi_worker.stop()
        elif word in ('a','confirm'):
            if m.page=='mpu':self.command('e' if self.mpu_zero_done else 'z',now)
            elif m.interaction_mode=='emg':self.command('e',now)
            elif m.interaction_mode=='eeg':self.command({'eeg':'mi','mi':'ssvep'}.get(m.page,'monitor'),now)
        elif word in ('open','close','start','left','right'):m.tasks.action(word)
        else:raise ValueError('未知操作；输入 help 查看按键')
    def tick(self,now,rows=(),state='waiting',brain=None,display=None,stm=None):
        m=self.menu
        for row in rows:
            self.model.observe(row)
            if self.pipeline:self.pipeline.observe(row)
        if state!='live':self.model.expire()
        m.raw=self.model.raw;m.rms=self.model.rms;m.pressed=self.model.pressed;m.signal_state=state
        if m.tasks.peer:
            if not m.tasks.peer.connected:m.tasks.enabled=False;m.message='控制连接已断开，请重新选择设备'
            else:m.status=m.tasks.peer.latest_status;m.tasks.sync(m.status)
        if stm:m.pendulum_raw=stm
        else:m.pendulum_raw=None
        if m.ssvep_active:
            if self.brain.epoch!=m.epoch:self.brain.start(m.epoch,now)
            if brain and display and 0<=now-display.get('received_at',-1e30)<=.6:
                m.scores=brain.get('scores');choice=self.brain.observe(brain,now,display)
                if choice is not None:m.brain_choice(choice,now)
            else:
                self.brain.clear('no_fresh_quality_passed_window');m.scores=None
            m.brain_reason=self.brain.reason
            if m.tasks.enabled and (not brain or brain.get('valid') is not True):m._stop(now,'脑电输入过期或质量未通过')
        if m.tasks.mode=='eye' and m.tasks.enabled and not self.simulation and (not self.eye or not self.eye.snapshot(now)['valid']):m._stop(now,'眼动输入过期，已停止')
        if m.media:m.media.tick()
        state=m.snapshot(now)
        state['timeline']=list(self.model.events)[-2:]+list(m.timeline)[-2:]
        state['pendulum_raw']=m.pendulum_raw
        state['pl_signal']=self.pipeline.last if self.pipeline and state['signal_state']=='live' else None
        state['eye_status']=self.eye.snapshot(now) if self.eye and m.interaction_mode=='eye' else None
        return state
    def close(self):
        try:self.menu.tasks.close()
        finally:
            if self.eye:self.eye.close();self.eye=None
            if self.menu.media:self.menu.media.close();self.menu.media=None
            if self.mi_worker:self.mi_worker.close();self.mi_worker=None

def preflight(board=False,eye_root=None):
    manifest_path=ROOT/'release/manifest.json'
    if not manifest_path.is_file():raise RuntimeError('release manifest missing')
    manifest=json.loads(manifest_path.read_text(encoding='utf8'))
    for name,wanted in manifest['files'].items():
        file=(ROOT/name).resolve()
        if ROOT.resolve() not in file.parents or hashlib.sha256(file.read_bytes()).hexdigest()!=wanted:raise RuntimeError('release checksum mismatch: '+name)
    if board:
        from coexist_guard import verify_release,BRAIN_ROOT,CoexistGuard
        from pynq import PL
        verify_release(BRAIN_ROOT);CoexistGuard(eye_root,PL.bitfile_name).check_runtime()
        for name in ('is4-calibration','libtobii_display.so'):
            if not (Path(eye_root)/name).is_file():raise RuntimeError('missing eye runtime: '+name)
    return dict(state='verified_files',files=len(manifest['files']),board_checked=board,physical_output_enabled=False)

HELP='PL_KEY0/Tab切模式 PL_KEY1/ESC停止 | c眼动连接/重标定 p确认位置 | e启用 zMPU置零 | monitor/mi/ssvep脑电任务 | mi-left/mi-right/mi-rest提示 | operate/process/technical/auxiliary切页 | q退出'

def preview(directory,font=None):
    from .render import Renderer
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True);renderer=Renderer(font)
    session=Session(SimulatedPeer,True)
    session.model.raw.extend([int(2050+90*math.sin(i*.3)) for i in range(500)])
    session.model.rms=63.6;session.model.pressed=False
    pages=[('operate','operate','home','eye',['灵巧手','倒立摆','表达与媒体']),
           ('expression','operate','speech','eye',['我想喝水','返回','我需要帮助']),
           ('media','operate','media','eye',['观看视频','返回','选择音乐']),
           ('process','process','process','eye',[]),('emg','emg','emg','emg',[]),
           ('eeg','eeg','eeg','eeg',[]),('mi','mi','mi','eeg',[]),
           ('brain','brain','ssvep_devices','eeg',['灵巧手','倒立摆','返回脑电','停止']),
           ('technical','technical','technical','eye',[])]
    for name,page,menu,mode,labels in pages:
        state=session.menu.snapshot(1);state.update(page=page,menu_page=menu,interaction_mode=mode,labels=labels,
                                                  raw=list(session.model.raw),rms=63.6,pressed=False,signal_state='live')
        renderer.render(state).save(directory/(name+'.png'))
    session.close();return dict(origin='simulation',preview_dir=str(directory.resolve()))

def run(args):
    from .render import Renderer
    from contextlib import ExitStack
    from pc_client import ControlClient
    commands=queue.Queue(maxsize=32)
    def read_commands():
        for line in sys.stdin:
            try:commands.put_nowait(line.strip())
            except queue.Full:pass
    threading.Thread(target=read_commands,daemon=True).start()
    session=Session(SimulatedPeer if args.simulate else lambda source:ControlClient(args.s3,source=source),args.simulate)
    renderer=Renderer(args.font);display=None;guide_renderer=None;last_display=None
    control=Path(args.control_dir);control.mkdir(parents=True,exist_ok=True)
    log=open(control/'session.jsonl','a',encoding='utf8');log_at=0;last_id=None;epoch=None
    def interrupted(*_):session.quit=True
    signal.signal(signal.SIGINT,interrupted);signal.signal(signal.SIGTERM,interrupted)
    print(HELP,flush=True)
    with ExitStack() as cleanup:
        cleanup.callback(log.close)
        from .media import MediaRouter
        media_root=Path(args.media_dir);legacy=Path(args.prepared_media)
        ratings=Path(args.ratings) if args.ratings else legacy/'ratings.json' if legacy.is_dir() and not args.simulate else control/'ratings.json'
        session.menu.media=MediaRouter(media_root,ratings,library_state=args.library_state,audio=SimulatedAudio() if args.simulate else None,
                                      audio_device=args.audio_device,prepared_root=legacy if not args.simulate else None)
        from .brain_display import BrainDisplay,MiWorker
        brain_display=BrainDisplay()
        if not args.simulate:
            preflight(True,args.eye_root)
            from .hdmi import HdmiDisplay
            display=HdmiDisplay(ROOT/'release/intent_one.bit',args.eye_root);cleanup.callback(display.close)
            from .pipeline import LiveSignalPipeline
            session.pipeline=LiveSignalPipeline(display.signal)
            stream=SignalConnection(args.s3);cleanup.callback(stream.close)
            try:stream.connect()
            except OSError:stream.reader.close();session.menu.message='S3采样未连接；眼控媒体仍可使用，设备控制需供电'
            stm=PendulumConnection(args.c3);cleanup.callback(stm.close)
            api=BrainApi();cleanup.callback(api.close)
            session.mi_worker=MiWorker(api.mi_command)
            if not args.no_buttons:
                from buttons import Buttons
                buttons=Buttons();cleanup.callback(buttons.close)
                from .controls import PsControls
                ps_controls=PsControls(buttons)
            else:buttons=None
        elif not args.headless:
            import tkinter as tk
            from PIL import ImageTk
            window=tk.Tk();window.title('我们意念合一 · 模拟演示');canvas=tk.Label(window);canvas.pack()
            window.bind('<Escape>',lambda _:commands.put_nowait('s'))
            window.bind('<Tab>',lambda _:commands.put_nowait('mode_next'))
            window.bind('<Return>',lambda _:commands.put_nowait('confirm'))
            def preview_click(event):
                if 238<=event.y<=490:
                    count=4 if session.menu.ssvep_active else 3
                    commands.put_nowait('choose '+str(min(count-1,max(0,event.x*count//1280))))
            canvas.bind('<Button-1>',preview_click)
            for key in ('1','2','3','4','5','6','e','s','z','q'):
                window.bind(key,lambda event:commands.put_nowait(event.char))
            window.protocol('WM_DELETE_WINDOW',lambda:commands.put_nowait('q'))
            cleanup.callback(window.destroy)
        cleanup.callback(session.close)
        deadline=time.monotonic()+args.seconds if args.seconds else float('inf')
        while not session.quit and time.monotonic()<deadline:
            now=time.monotonic();m=session.menu;guide=None
            pending=[]
            while len(pending)<8:
                try:pending.append(commands.get_nowait())
                except queue.Empty:break
            try:
                file=control/'command.json'
                if file.is_file() and file.stat().st_size<=4096:
                    row=json.loads(file.read_text());ident=row.get('id')
                    if ident!=last_id and type(ident) is str and type(row.get('updated_monotonic')) in (int,float) and 0<=now-row['updated_monotonic']<=1:
                        last_id=ident;pending.append(row.get('action',''))
                if not args.simulate and buttons:
                    pending.extend(ps_controls.poll(now,m.interaction_mode,session.eye.guide.phase if session.eye and m.interaction_mode=='eye' else m.page))
                if not args.simulate and not args.no_buttons:pending.extend(display.buttons.poll(now))
                if 'stop' in pending or 's' in pending:pending=[word for word in pending if word not in ('mode_next','e','enable','confirm','a')]
                for command in pending:
                    if command=='help':print(HELP,flush=True)
                    elif command=='c' and not args.simulate:
                        m.tasks.estop()
                        if m.media:m.media.stop()
                        if session.eye:session.eye.close()
                        from guardianloop_system.live_inputs import EyeInputs
                        from guide_render import Renderer as GuideRenderer
                        session.eye=EyeInputs(Path(args.eye_root));guide_renderer=GuideRenderer(font=args.font,live=True,relative=True,selection_test=True)
                    elif command=='p' and session.eye:session.eye.confirm_position(now)
                    elif command=='pause' and session.eye and session.eye.guide.phase!='selection':
                        m.tasks.estop();session.eye.close();session.eye=None;m.message='校准已取消；PS_KEY0重新连接'
                    elif command=='b' and display:
                        m.tasks.estop()
                        from .benchmark import compare
                        samples=[int(2050+90*math.sin(i*.3)) for i in range(1000)]
                        answer=compare(display.signal,samples);(control/'benchmark.json').write_text(json.dumps(answer,indent=2))
                        session.pipeline.reset()
                        m.benchmark=answer;m.page_to('technical',now)
                    else:session.command(command,now)
                if session.mi_worker and (m.interaction_mode!='eeg' or m.page!='mi') and session.mi_worker.snapshot().get('target') is not None:session.mi_worker.stop()
                if session.eye and m.interaction_mode=='eye':guide=session.eye.poll(m,now)
                if args.simulate:state=session.tick(now)
                else:
                    brain_active=m.ssvep_active
                    if epoch!=m.epoch:epoch=m.epoch;last_display=None
                    counters=display.stimulus.tick(m.epoch,brain_active,now)
                    if counters:last_display=counters
                    lease={'mode':'live_readonly_hdmi','page':'drive' if brain_active else 'home','updated_monotonic':now,'physical_output_enabled':False}
                    leasefile=Path(args.page_lease);part=leasefile.with_suffix('.part');part.write_text(json.dumps(lease));part.replace(leasefile)
                    with stream.lock:signal_state=stream.reader.snapshot(now)['state']
                    state=session.tick(now,stream.poll(),signal_state,api.candidate(now),last_display,stm.poll(now))
                    status=api.read('status',now)
                    state['monitor']=status if status and status.get('stale') is False else None
                    state['brain_display']=brain_display.observe(status,api.read('mi-cue',now))
                    state['mi_trial']=session.mi_worker.snapshot()
                image=guide_renderer.render(guide) if guide and session.eye.guide.phase!='selection' else renderer.render(state,video_image=m.media.picture if m.media and m.page in ('video','video_nav','video_rate') else None)
                if args.simulate and not args.headless:
                    canvas.image=ImageTk.PhotoImage(image);canvas.configure(image=canvas.image);window.update()
                elif args.simulate:
                    if now-log_at>=1:image.save(control/'last_frame.png')
                else:
                    try:display.present(image,now)
                    except (RuntimeError,OSError):
                        session.quit=True
                        raise
                if guide and session.eye.guide.phase!='selection':session.eye.presented(guide,time.monotonic())
                else:m.presented(time.monotonic())
                if session.mi_worker and m.page=='mi':session.mi_worker.presented(time.monotonic())
                if now-log_at>=1:
                    log.write(json.dumps(dict(time_monotonic=now,state=state),ensure_ascii=False)+'\n');log.flush();log_at=now
                    part=control/'state.json.part';part.write_text(json.dumps(state,ensure_ascii=False));part.replace(control/'state.json')
            except (RuntimeError,ValueError,OSError) as exc:
                try:m.tasks.estop()
                except (RuntimeError,OSError):pass
                m.message=str(exc);print('session_error='+str(exc),flush=True)
                if not args.simulate and display is None:raise
            time.sleep(max(.005,.05-(time.monotonic()-now)))

def main(argv=None):
    p=argparse.ArgumentParser(description='我们意念合一：独立输入，单屏实验系统')
    p.add_argument('command',choices=('preflight','preview','run'))
    p.add_argument('--simulate',action='store_true');p.add_argument('--board',action='store_true')
    p.add_argument('--headless',action='store_true',help='simulation verification without opening a window')
    p.add_argument('--s3',default='192.168.4.2');p.add_argument('--c3',default='192.168.4.1')
    p.add_argument('--eye-root',default='/home/xilinx/tobii_z15');p.add_argument('--font')
    p.add_argument('--media-dir',default='/home/xilinx/tobii_z15/media');p.add_argument('--audio-device')
    p.add_argument('--prepared-media',default='/home/xilinx/gl-media-20261007-314e8796');p.add_argument('--library-state')
    p.add_argument('--ratings')
    p.add_argument('--preview-dir',default=str(ROOT/'report/preview'));p.add_argument('--seconds',type=int,default=0)
    p.add_argument('--control-dir',default='/dev/shm/intent_one')
    p.add_argument('--page-lease',default='/dev/shm/gl-media-20261007-314e8796-system-page.json')
    p.add_argument('--no-buttons',action='store_true');args=p.parse_args(argv)
    if args.headless and not args.simulate:raise ValueError('--headless is only for explicit simulation')
    if args.command=='preflight':print(json.dumps(preflight(args.board,args.eye_root),ensure_ascii=False))
    elif args.command=='preview':print(json.dumps(preview(args.preview_dir,args.font),ensure_ascii=False))
    else:run(args)
if __name__=='__main__':main()
