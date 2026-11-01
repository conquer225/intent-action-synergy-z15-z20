"""Interactive localhost rehearsal with recorded inputs and software integers."""
import argparse,json,secrets,threading,time
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from .feature_runtime import FeatureRuntime
from .training import ModelBundle
from .headless_display import HeadlessDisplay
from .visual_demo import DemoState
from .visual_server import DemoServer
from .visual_pipeline import VisualPipeline
from .visual_host import VisualHost,start_http
from .visual_profile import CaptureProfile


class OfflineBoard:
    """Reuse the production producers/display without opening any hardware."""
    def __init__(self,root):
        self.root=Path(root).resolve();self.threads=[];self.cleanup=ExitStack()
        self.token=secrets.token_hex(24);self.state=DemoState()

    def __enter__(self):
        root=self.root
        assets=root/'assets' if (root/'assets/sound').is_dir() else root/'artifacts/headless'
        models=root/'models' if (root/'models/sound').is_dir() else root/'artifacts/headless/models'
        try:
            self.runtime=FeatureRuntime({task:ModelBundle.load(models/task) for task in ('sound','fatigue','emotion') if (models/task/'weights.npz').is_file()})
            self.cleanup.callback(self.runtime.close)
            run=root/'run/offline';run.mkdir(parents=True,exist_ok=True)
            self.pipeline=SimpleNamespace(renderer=HeadlessDisplay(assets/'display/glyphs.npz'),
                lock=threading.Lock(),stopped=threading.Event(),runtime=self.runtime,
                sound_root=assets/'sound',frames=0,display_matches=0,display=None,preview=run/'board-frame.png')
            self.visual=VisualPipeline(self.pipeline,self.state)
            self.cleanup.callback(self._stop_workers)
            for target in (self.visual.audio_loop,self.visual.render_loop):
                thread=threading.Thread(target=target,daemon=True);self.threads.append(thread);thread.start()
            self.server=self.cleanup.enter_context(DemoServer(self.state,'127.0.0.1',0,0,token=self.token))
            return self
        except BaseException:self.cleanup.close();raise

    def _stop_workers(self):
        self.pipeline.stopped.set()
        for thread in self.threads:thread.join(4)
        if any(thread.is_alive() for thread in self.threads):raise RuntimeError('offline worker did not stop')

    def __exit__(self,*args):return self.cleanup.__exit__(*args)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=float,default=0)
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--without-depth',action='store_true')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    errors=[];profile=CaptureProfile();started=time.monotonic();captures=0
    with OfflineBoard(root) as board,ExitStack() as cleanup:
        replay=root/'assets/replay/scene-bgr.npy'
        if not replay.is_file():replay=root/'build/navigator/scene-bgr.npy'
        model=root/'build/reconstruction/models/yolo26m-depth.pt'
        host=VisualHost('127.0.0.1',board.token,control_port=board.server.control_port,
            frame_port=board.server.frame_port,model=None if args.without_depth else model,
            replay_npy=replay).start()
        cleanup.callback(host.close)
        web=start_http(host,0);cleanup.callback(web.server_close);cleanup.callback(web.shutdown)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(channel='chrome',headless=args.headless)
            page=browser.new_page(viewport=dict(width=960,height=540),device_scale_factor=1)
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto('http://127.0.0.1:%d/'%web.server_port)
            page.wait_for_function('window.demoReady===true',timeout=30000)
            print('OFFLINE_READY: mouse buttons / Left, Enter, Right / Escape; recorded sources, software only',flush=True)
            while not page.is_closed() and (not args.seconds or time.monotonic()-started<args.seconds):
                tick=time.monotonic();before=page.evaluate('window.demoBinding')
                jpeg=page.screenshot(type='jpeg',quality=profile.quality);after=page.evaluate('window.demoBinding')
                if before and before==after:host.queue(jpeg,after);captures+=1
                if profile.observe(now=time.monotonic(),sent=host.sent):
                    page.set_viewport_size(dict(width=profile.size[0],height=profile.size[1]))
                page.wait_for_timeout(max(1,int((1/profile.fps-(time.monotonic()-tick))*1000)))
            browser.close()
        report=dict(captured_frames=captures,received_frames=board.state.accepted_frames,
            browser_errors=errors,elapsed_seconds=time.monotonic()-started,
            profile=dict(size=profile.size,quality=profile.quality,target_fps=profile.fps),
            physical_wifi=False,physical_hdmi=False,physical_pl=False,source='recorded PCM and historical camera frame',
            passed=not errors and board.state.accepted_frames>0)
        (root/'run/offline/report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
        return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
