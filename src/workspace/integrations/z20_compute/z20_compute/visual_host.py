"""PC visual host: offline local assets, optional depth, and JPEG return to Z20."""
import argparse,base64,hashlib,json,socket,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,unquote
from urllib.request import urlopen
import numpy as np
from .visual_server import DemoClient,DemoServer
from .visual_demo import DemoState
from .visual_wire import write_json,read_json,write_frame
from .wireless_only import require_wireless

ROOT=Path(__file__).resolve().parents[1]


class VisualHost:
    def __init__(self,host,token,*,control_port=9022,frame_port=9023,http_port=9021,model=None,replay_npy=None):
        self.host,self.token,self.control_port,self.frame_port,self.http_port=host,token,control_port,frame_port,http_port
        self.model,self.replay_npy=model,replay_npy
        self.lock=threading.Lock();self.stopped=threading.Event()
        self.state={};self.cloud=dict(valid=False);self.images={};self.spatial_key=None
        self.renderer=self.controller=None;self.pending=None;self.sent=0;self.dropped=0;self.sequence=0
        self.label='离线回环联调' if host=='127.0.0.1' else 'USB Wi-Fi 无线回传'
        self.threads=[];self.runner=None;self.depth_busy=False

    def start(self):
        for target in (self._poll,self._send):
            thread=threading.Thread(target=target,daemon=True);self.threads.append(thread);thread.start()
        return self

    def snapshot(self):
        with self.lock:
            value=dict(self.state,transport_label=self.label,pc_frames_sent=self.sent,
                spatial_ready=self.cloud.get('valid',False),spatial_message=getattr(self,'depth_message','等待新鲜相机帧'))
            return value

    def command(self,name):
        if name not in ('left','right','enter','back','stop','recorded_sound_0','recorded_sound_1','recorded_sound_2'):raise ValueError('unknown demo action')
        with self.lock:client=self.controller
        if client is None:raise ConnectionError('board control channel unavailable')
        result=client.command(name)
        with self.lock:
            if (self.controller is client and result.get('session')==self.state.get('session')
                    and result.get('epoch',-1)>=self.state.get('epoch',-1)):
                self.state=result
        return result

    def sound_input(self,data,*,microphone=False):
        from .sound_input import decode_sound_wav,prepare_sound_input
        sample=prepare_sound_input(decode_sound_wav(data),source='live:pc_microphone' if microphone else 'recorded:pc_wav')
        with self.lock:client=self.controller
        if client is None:raise ConnectionError('Z20 未连接')
        reply=client.sound_input(**sample)
        with self.lock:
            if self.controller is client and reply.get('epoch',-1)>=self.state.get('epoch',-1):self.state=reply
        if not reply.get('accepted'):raise ValueError('请先进入 NPU 分类页面，再采集声音')
        return dict(accepted=True,window_id=sample['window_id'],valid=sample['valid'])

    def _poll(self):
        while not self.stopped.is_set():
            try:
                require_wireless(self.host,allow_loopback=self.host=='127.0.0.1')
                with DemoClient(self.host,self.control_port,token=self.token,role='renderer') as renderer, \
                     DemoClient(self.host,self.control_port,token=self.token,role='controller') as controller:
                    with self.lock:self.renderer,self.controller=renderer,controller
                    while not self.stopped.is_set():
                        state=renderer.status()
                        controller.status()  # Keep the idle manual-control channel alive during browser startup.
                        key=(state['session'],state['epoch'])
                        with self.lock:
                            # A renderer poll can have started before a newer
                            # command ACK. Never roll its mode/epoch back.
                            if (state['session']==self.state.get('session')
                                    and state['epoch']<self.state.get('epoch',-1)):
                                continue
                            self.state=state
                            if key!=self.spatial_key:
                                self.cloud=dict(valid=False);self.images={}
                            start=(not state['menu'] and state['mode']=='spatial' and key!=self.spatial_key and not self.depth_busy)
                            if start:self.spatial_key=key;self.depth_busy=True
                        if start:
                            threading.Thread(target=self._depth,args=(key,),daemon=True).start()
                        self.stopped.wait(.08)
            except (OSError,ValueError,RuntimeError,EOFError):
                with self.lock:
                    self.state=dict(self.state,renderer_online=False);self.renderer=self.controller=None;self.pending=None
                self.stopped.wait(.5)

    def queue(self,jpeg,binding):
        with self.lock:
            if (not binding or binding.get('session')!=self.state.get('session')
                    or binding.get('epoch')!=self.state.get('epoch')):return
            if self.pending is not None:self.dropped+=1
            self.pending=(bytes(jpeg),dict(binding))

    def _send(self):
        while not self.stopped.is_set():
            try:
                with self.lock:session=self.state.get('session')
                if not session:self.stopped.wait(.1);continue
                require_wireless(self.host,allow_loopback=self.host=='127.0.0.1')
                with socket.create_connection((self.host,self.frame_port),timeout=2) as sock:
                    sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                    with sock.makefile('rwb') as stream:
                        write_json(stream,dict(token=self.token,session=session))
                        if not read_json(stream).get('ok'):raise PermissionError('frame channel rejected')
                        while not self.stopped.is_set():
                            with self.lock:
                                pending=self.pending;self.pending=None;current=self.state.copy()
                            if current.get('session')!=session:break
                            if pending:
                                jpeg,binding=pending
                                if binding['epoch']!=current.get('epoch'):continue
                                self.sequence+=1
                                write_frame(stream,session,binding['epoch'],self.sequence,jpeg)
                                if read_json(stream).get('accepted'):self.sent+=1
                            self.stopped.wait(.005)
            except (OSError,ValueError,RuntimeError,EOFError):self.stopped.wait(.3)

    def _depth(self,key):
        import cv2
        try:
            self.depth_message='正在读取相机画面'
            if self.replay_npy:
                original=np.load(self.replay_npy,allow_pickle=False)
                if original.shape!=(720,1280,3):raise ValueError('legacy replay requires 720x1280 BGR')
                image=cv2.resize(original[:,:640],(640,480))
                metadata=dict(source='recorded:legacy_camera_frame',preprocessing='legacy squeezed half restored to 640x480')
            else:
                with urlopen('http://%s:%d/demo/camera.ppm'%(self.host,self.http_port),timeout=5) as response:
                    data=response.read(2*1024*1024+1)
                    if len(data)>2*1024*1024:raise ValueError('camera image too large')
                    metadata=json.loads(response.headers['X-Camera-Metadata'])
                image=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
                if image is None:raise ValueError('camera snapshot decoding failed')
            with self.lock:
                if key!=(self.state.get('session'),self.state.get('epoch')):return
                self.images['original.png']=cv2.imencode('.png',image)[1].tobytes()
            if self.model is None:raise RuntimeError('depth checkpoint not configured')
            self.depth_message='正在生成相对深度与可见表面'
            from .mono_depth import YoloDepthRunner,export_monocular_preview
            from .depth_surface import depth_surface
            if self.runner is None:self.runner=YoloDepthRunner(self.model)
            depth,model_meta=self.runner.infer(image)
            directory=ROOT/'artifacts/visual-demo/captures'/key[0]/str(key[1])
            record=export_monocular_preview(image,depth,directory,focal_px=600*image.shape[1]/640.,model_name=Path(self.model).name)
            record.update(model_meta,input=metadata,session=key[0],epoch=key[1],
                input_sha256=hashlib.sha256(image.tobytes()).hexdigest())
            (directory/'result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
            relative=depth/np.median(depth[np.isfinite(depth)&(depth>0)])
            h,w=depth.shape;focal=600*w/640.
            surface=depth_surface(relative,image,np.array([[focal,0,w/2],[0,focal,h/2],[0,0,1]]),stride=4)
            cloud=dict(valid=True,id=key[0]+':'+str(key[1]),units='relative_depth_median',metric_verified=False,
                points=surface.vertices.round(5).ravel().tolist(),colors=(surface.colors.astype(float)/255).round(3).ravel().tolist())
            with self.lock:
                if key!=(self.state.get('session'),self.state.get('epoch')):return
                self.cloud=cloud;self.images['depth.png']=(directory/'depth-preview.png').read_bytes()
            self.depth_message='相对深度可见表面已生成'
        except Exception as exc:self.depth_message=type(exc).__name__+': '+str(exc)
        finally:self.depth_busy=False

    def close(self):
        self.stopped.set()
        for thread in self.threads:thread.join(4)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        host=self.server.visual;path=unquote(urlsplit(self.path).path)
        if path=='/api/state':body=json.dumps(host.snapshot(),allow_nan=False).encode();kind='application/json'
        elif path=='/api/cloud':
            with host.lock:body=json.dumps(host.cloud).encode()
            kind='application/json'
        elif path in ('/api/original.png','/api/depth.png'):
            with host.lock:body=host.images.get(path.split('/')[-1])
            if body is None:self.send_error(404);return
            kind='image/png'
        else:
            folder=ROOT/'third_party/visual' if path.startswith('/vendor/') else ROOT/'web/visual_demo'
            relative=path[len('/vendor/'):] if path.startswith('/vendor/') else path.lstrip('/') or 'index.html'
            target=(folder/relative).resolve()
            try:target.relative_to(folder.resolve())
            except ValueError:self.send_error(403);return
            if not target.is_file():self.send_error(404);return
            body=target.read_bytes();kind={'.html':'text/html; charset=utf-8','.js':'text/javascript','.png':'image/png'}.get(target.suffix,'application/octet-stream')
        self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)

    def do_POST(self):
        try:
            if self.path not in ('/api/command','/api/sound'):self.send_error(404);return
            origin=self.headers.get('Origin')
            if origin not in (None,'http://127.0.0.1:%d'%self.server.server_port):raise ValueError('cross-origin command rejected')
            size=int(self.headers.get('Content-Length','0'))
            limit=2*1024*1024 if self.path=='/api/sound' else 4096
            if not 0<size<=limit:raise ValueError('invalid input length')
            data=self.rfile.read(size)
            result=(self.server.visual.sound_input(data,microphone=self.headers.get('X-Sound-Source')=='microphone')
                    if self.path=='/api/sound' else self.server.visual.command(json.loads(data).get('name')))
            body=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        except (ValueError,OSError,EOFError) as exc:self.send_error(400,str(exc))

    def log_message(self,*_):pass


def start_http(host,port=9140):
    server=ThreadingHTTPServer(('127.0.0.1',port),_Handler);server.visual=host
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True);parser.add_argument('--token-file',type=Path,required=True)
    parser.add_argument('--model',type=Path);parser.add_argument('--offline',action='store_true')
    parser.add_argument('--replay-npy',type=Path);parser.add_argument('--seconds',type=float,default=0)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/visual-demo/pc-run.json')
    args=parser.parse_args();route=require_wireless(args.host,allow_loopback=args.offline)
    if args.replay_npy and not args.offline:parser.error('recorded camera input is offline-only')
    host=VisualHost(args.host,args.token_file.read_text().strip(),model=args.model,replay_npy=args.replay_npy).start()
    server=start_http(host)
    from playwright.sync_api import sync_playwright
    from .visual_profile import CaptureProfile
    profile=CaptureProfile();started=time.monotonic();captures=0
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(channel='chrome',headless=False,args=['--disable-background-timer-throttling'])
            page=browser.new_page(viewport=dict(width=960,height=540),device_scale_factor=1)
            page.goto('http://127.0.0.1:9140/');page.wait_for_function('window.demoReady===true',timeout=30000)
            while not args.seconds or time.monotonic()-started<args.seconds:
                tick=time.monotonic();before=page.evaluate('window.demoBinding')
                jpeg=page.screenshot(type='jpeg',quality=profile.quality)
                after=page.evaluate('window.demoBinding')
                if before and before==after:host.queue(jpeg,after);captures+=1
                if profile.observe(now=time.monotonic(),sent=host.sent):
                    page.set_viewport_size(dict(width=profile.size[0],height=profile.size[1]))
                page.wait_for_timeout(max(1,int((1/profile.fps-(time.monotonic()-tick))*1000)))
            browser.close()
    finally:
        report=dict(route=route,captured_frames=captures,sent_frames=host.sent,replaced_pending_frames=host.dropped,
            elapsed_seconds=time.monotonic()-started,profile=dict(size=profile.size,quality=profile.quality,target_fps=profile.fps),physical_wireless_verified=False,
            note='Route check is not a completed hardware throughput acceptance test.')
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        host.close();server.shutdown();server.server_close()


if __name__=='__main__':main()
