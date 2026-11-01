"""Real browser/JPEG/TCP loopback acceptance; explicitly no PL, Wi-Fi or HDMI."""
import argparse,json,threading,time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from z20_compute.visual_demo import DemoState
from z20_compute.visual_server import DemoServer
from z20_compute.visual_host import VisualHost,start_http
from z20_compute.visual_pipeline import VisualPipeline
from z20_compute.headless_display import HeadlessDisplay
from z20_compute.feature_runtime import FeatureRuntime
from z20_compute.training import ModelBundle

ROOT=Path(__file__).resolve().parent


class MemoryDisplay:
    def __init__(self):self.frame=None;self.frames=0
    def show(self,frame):self.frame=frame;self.frames+=1
    def readback(self):return self.frame


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--depth',action='store_true')
    parser.add_argument('--soak-seconds',type=float,default=0)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/visual-demo/loopback')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    state=DemoState();runtime=FeatureRuntime({task:ModelBundle.load(ROOT/'artifacts/headless/models'/task) for task in ('fatigue','emotion','sound')})
    display=MemoryDisplay()
    pipeline=SimpleNamespace(renderer=HeadlessDisplay(ROOT/'artifacts/headless/display/glyphs.npz'),
        lock=threading.Lock(),stopped=threading.Event(),runtime=runtime,
        sound_root=ROOT/'artifacts/headless/sound',frames=0,display_matches=0,display=display,
        preview=args.output/'board-frame.png')
    visual=VisualPipeline(pipeline,state)
    threads=[threading.Thread(target=fn,daemon=True) for fn in (visual.audio_loop,visual.render_loop)]
    for thread in threads:thread.start()
    model=ROOT/'build/reconstruction/models/yolo26m-depth.pt' if args.depth else None
    replay=ROOT/'build/navigator/scene-bgr.npy' if args.depth else None
    errors=[];requests=[];checks={};started=time.monotonic();soak=None
    with DemoServer(state,'127.0.0.1',0,0,token='offline-test-only') as board:
        host=VisualHost('127.0.0.1','offline-test-only',control_port=board.control_port,frame_port=board.frame_port,
            model=model,replay_npy=replay).start()
        web=start_http(host,0)
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(channel='chrome',headless=True,
                    args=['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'])
                page=browser.new_page(viewport=dict(width=960,height=540),device_scale_factor=1,permissions=['microphone'])
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('request',lambda request:requests.append(request.url))
                page.goto('http://127.0.0.1:%d/'%web.server_port)
                page.wait_for_function('window.demoReady===true',timeout=30000)
                def capture(name,seconds=2):
                    begin=time.monotonic();sent=0
                    while time.monotonic()-begin<seconds:
                        before=page.evaluate('window.demoBinding')
                        jpeg=page.screenshot(type='jpeg',quality=70)
                        after=page.evaluate('window.demoBinding')
                        if before and before==after:host.queue(jpeg,after);sent+=1
                        page.wait_for_timeout(30)
                    page.screenshot(path=str(args.output/(name+'.png')))
                    if state.snapshot()['mode']=='npu' and display.frame is not None:
                        import cv2
                        local=np.frombuffer(display.frame,np.uint8).reshape(720,1280,3)
                        cv2.imwrite(str(args.output/(name+'-local.png')),local[...,::-1])
                    return sent
                host.command('enter');capture('fluid')
                for _ in range(10):host.command('left');host.command('right')
                capture('fluid-injected')
                import cv2
                pixels=cv2.imread(str(args.output/'fluid-injected.png'))[100:430]
                checks['fluid_visible_pixels']=int((np.ptp(pixels.astype(np.int16),axis=2)>35).sum())>1000
                for frame in page.frames:
                    if frame.url.endswith('/fluid.html'):
                        print('FLUID_STATE',frame.evaluate('({paused:config.PAUSED,last:last,width:canvas.width,height:canvas.height,lost:gl.isContextLost(),error:gl.getError(),dye:[dye.width,dye.height],velocity:[velocity.width,velocity.height]})'),flush=True)
                        frame.locator('canvas').screenshot(path=str(args.output/'fluid-canvas.png'))
                checks['fluid_action_count']=state.action_id==20
                host.command('back');host.command('right');host.command('enter');capture('spectrum',3)
                details=state.snapshot()['data'].get('spectrum',{})
                checks['real_spectrum_history']=len(details.get('history',[]))>5
                checks['silent']=details.get('playback_started') is False
                host.command('back');host.command('right');host.command('enter');capture('npu-fatigue',2)
                checks['fatigue_features']=len(state.snapshot()['data'].get('npu',{}).get('features',[]))==20
                host.command('right');capture('npu-emotion',2)
                checks['emotion_features']=len(state.snapshot()['data'].get('npu',{}).get('features',[]))==180
                host.command('right');capture('npu',3)
                trace=state.snapshot()['data'].get('npu',{})
                checks['recorded_npu_input']=len(trace.get('features',[]))==40
                checks['software_marked']=trace.get('backend')=='PS_integer_reference'
                checks['navigation_not_covered_by_sound_controls']=page.evaluate('''() => {
                    const a=document.querySelector('#sound-controls').getBoundingClientRect(),b=document.querySelector('footer').getBoundingClientRect();
                    return a.bottom<=b.top+1 && b.bottom<=innerHeight+1;
                }''')
                page.locator('#record-sound').click()
                page.wait_for_function("document.querySelector('#record-sound').disabled===false",timeout=10000)
                capture('npu-browser-microphone',1)
                captured=state.snapshot()['data'].get('npu',{})
                checks['browser_microphone_adapter']=captured.get('source')=='live:pc_microphone' and captured.get('event')=='completed'
                page.set_viewport_size(dict(width=640,height=360));capture('npu-compact',.5)
                checks['compact_navigation_visible']=page.evaluate("document.querySelector('footer').getBoundingClientRect().bottom<=innerHeight+1")
                page.set_viewport_size(dict(width=960,height=540))
                if args.depth:
                    host.command('back');host.command('right');host.command('enter')
                    deadline=time.monotonic()+55
                    while not host.cloud.get('valid') and time.monotonic()<deadline:
                        capture('spatial-progress',.3)
                    capture('spatial-original');host.command('right');capture('spatial-depth')
                    host.command('right');capture('spatial-cloud')
                    checks['recorded_depth']=host.cloud.get('valid') is True
                if args.soak_seconds:
                    host.command('back')
                    while state.snapshot()['mode']!='fluid':host.command('right')
                    host.command('enter')
                    begin=time.monotonic();frames=state.accepted_frames;ack=[]
                    while time.monotonic()-begin<args.soak_seconds:
                        tick=time.monotonic();host.command('left' if len(ack)%2==0 else 'right');ack.append((time.monotonic()-tick)*1000)
                        capture('soak-last',min(2,args.soak_seconds-(time.monotonic()-begin)))
                    elapsed=time.monotonic()-begin
                    soak=dict(seconds=elapsed,received_frames=state.accepted_frames-frames,
                        received_fps=(state.accepted_frames-frames)/elapsed,command_ack_p95_ms=float(np.percentile(ack,95)),
                        physical_wireless=False,mode='fluid',note='desktop loopback, not full physical combined acceptance')
                    checks['soak_completed']=elapsed>=args.soak_seconds and not errors
                browser.close()
            checks['received_frames']=state.accepted_frames>10
            checks['memory_display_frames']=display.frames>10
            checks['no_external_requests']=all(url.startswith('http://127.0.0.1:') or url.startswith(('data:','blob:')) for url in requests)
            checks['browser_errors']=not errors
        finally:
            host.close();web.shutdown();web.server_close()
    pipeline.stopped.set()
    for thread in threads:thread.join(4)
    runtime.close()
    report=dict(passed=all(checks.values()),checks=checks,browser_errors=errors,
        accepted_frames=state.accepted_frames,memory_display_frames=display.frames,
        elapsed_seconds=time.monotonic()-started,physical_wifi=False,physical_pl=False,physical_hdmi=False,
        input='existing recorded PCM; browser-generated test microphone, not physical microphone; optional historical camera image',soak=soak)
    (args.output/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2));return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
