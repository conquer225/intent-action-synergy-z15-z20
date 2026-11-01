"""Explicitly bound TCP feature endpoint and read-only HTTP status surface."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import signal
import os
import socket
import threading
import time

from .feature_runtime import FeatureRuntime
from .headless_keys import Navigation
from .headless_preview import preview_fresh
from .service import BoardSession
from .training import ModelBundle
from .headless_readiness import load_enabled_models


HTML = '''<!doctype html><html lang="zh"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Z20 无屏联调</title>
<style>body{font:17px system-ui;max-width:1050px;margin:32px auto;padding:0 20px;color:#171717}
table{width:100%;border-collapse:collapse}td,th{padding:10px;text-align:left;border-bottom:1px solid #ccc}
pre{white-space:pre-wrap;word-break:break-word}img{width:100%;height:auto}</style>
<h1>Z20 无屏联调</h1><p>静音运行 · 辅助结果供 Z15 汇总 · 执行控制保持原链路</p>
<p id="link">正在连接板端状态…</p><table><thead><tr><th>任务</th><th>状态</th><th>结果</th><th>来源 / 窗口</th></tr></thead><tbody id="tasks"></tbody></table>
<p id="preview">板端显示预览尚未接入</p><img id="frame" hidden alt="板端渲染画面">
<details><summary>诊断详情</summary><pre id="details"></pre></details>
<script>
const names={emotion:'情绪',fatigue:'疲劳',sound:'声音',person_dog:'人狗关系',depth:'双目测距',cloud:'点云',audio:'音频分析',adda:'AD/DA'};
const labels={emotion:['负向','中性','正向'],fatigue:['清醒','轻度疲劳','重度疲劳'],sound:['拍手','口哨','敲击']};
async function tick(){try{
 const response=await fetch('/status.json',{cache:'no-store'});if(!response.ok)throw Error(response.status);
 const s=await response.json(); document.querySelector('#link').textContent='板端在线；数据端：'+(s.connected?'已连接':'等待连接')+'；页面：'+s.page;
 const body=document.querySelector('#tasks');body.replaceChildren();
 for(const [task,r] of Object.entries({...s.results,...(s.environment||{})})){
  let value='无有效结果';if(r.valid){value=labels[task]?labels[task][r.class_id]:JSON.stringify(r.payload);}
  const tr=document.createElement('tr');for(const text of [names[task]||task,r.state,
   value,(r.source||'')+' / '+(r.window_id||r.frame_id||'')]){
   const td=document.createElement('td');td.textContent=text;tr.appendChild(td);}body.appendChild(tr);}
 document.querySelector('#details').textContent=JSON.stringify(s,null,2);
 if(s.preview_available){const img=document.querySelector('#frame');img.hidden=false;img.src='/frame.png?t='+Date.now();document.querySelector('#preview').textContent='板端渲染画面';}
 else{document.querySelector('#frame').hidden=true;document.querySelector('#preview').textContent='等待新画面';}
 }catch(e){document.querySelector('#link').textContent='连接中断，当前结果已清空';document.querySelector('#tasks').replaceChildren();document.querySelector('#frame').hidden=true;}
}tick();setInterval(tick,1000);
</script></html>'''.encode('utf-8')


class StatusHTTP(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, snapshot, *, preview=None,analysis=None,cloud=None,cloud_file=None,visual_camera=None):
        self.snapshot, self.preview = snapshot, preview
        self.analysis=analysis
        self.cloud,self.cloud_file=cloud,cloud_file
        self.visual_camera=visual_camera
        super().__init__(address, StatusHandler)


class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path=='/demo/camera.ppm' and self.server.visual_camera is not None:
            result=self.server.visual_camera()
            if result is None:self.send_error(503,'fresh camera image unavailable');return
            meta,payload=result
            self.send_response(200);self.send_header('Content-Type','image/x-portable-pixmap')
            self.send_header('X-Camera-Metadata',json.dumps(meta,ensure_ascii=True))
            self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store')
            self.end_headers();self.wfile.write(payload);return
        if path == '/':
            payload, content_type, status = HTML, 'text/html; charset=utf-8', 200
        elif path == '/status.json':
            payload = json.dumps(self.server.snapshot(), allow_nan=False).encode('utf-8')
            content_type, status = 'application/json', 200
        elif path == '/audio.json' and self.server.analysis is not None:
            payload=json.dumps(self.server.analysis(),allow_nan=False).encode('utf-8')
            content_type,status='application/json',200
        elif path == '/cloud.json' and self.server.cloud is not None:
            payload=json.dumps(self.server.cloud(),allow_nan=False).encode('utf-8')
            content_type,status='application/json',200
        elif path == '/cloud.ply' and self.server.cloud_file is not None:
            payload=self.server.cloud_file()
            payload,content_type,status=(payload,'application/octet-stream',200) if payload else (b'no valid cloud','text/plain',404)
        elif path == '/frame.png' and self.server.preview is not None and preview_fresh(self.server.preview):
            payload, content_type, status = self.server.preview.read_bytes(), 'image/png', 200
        elif path == '/frame.json' and self.server.preview is not None and preview_fresh(self.server.preview):
            payload=self.server.preview.with_suffix('.json').read_bytes()
            content_type,status='application/json',200
        else:
            payload, content_type, status = b'not available', 'text/plain', 404
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_): pass


def open_npu():
    from .backend import HardwareNPU
    from .linux import UioRegisters, UioDmaAllocator
    def device(name):
        matches = [p for p in Path('/sys/class/uio').glob('uio*') if (p/'name').read_text().strip() == name]
        if len(matches) != 1: raise ValueError('expected one '+name)
        return matches[0]
    reg, ram = device('navigator-mlp'), device('navigator-npu-dma')
    registers = UioRegisters('/dev/'+reg.name, reg/'maps/map0', expected_address=0x40000000)
    try:
        pool = UioDmaAllocator('/dev/'+ram.name, ram/'maps/map0', '/proc/device-tree/reserved-memory/npu@2000000')
    except BaseException:
        registers.close(); raise
    return HardwareNPU(registers, pool, timeout=2), pool, registers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=9020)
    parser.add_argument('--http-port', type=int, default=9021)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--backend', choices=('pl', 'ps'), default='pl')
    parser.add_argument('--preview', type=Path)
    parser.add_argument('--display-assets',type=Path)
    parser.add_argument('--media-root',type=Path)
    parser.add_argument('--sound-root',type=Path)
    parser.add_argument('--hdmi',action='store_true')
    parser.add_argument('--keys',action='store_true')
    parser.add_argument('--calibration',type=Path,help='PC-exported metric maps for the exact observer mode')
    parser.add_argument('--record-pairs',type=Path,help='record at most 20 static chessboard pairs, every 2s')
    parser.add_argument('--visual-token-file',type=Path,help='enable four modes using a private demo token')
    parser.add_argument('--visual-codec',type=Path,help='ARM libz20_visual.so for the original userspace')
    args = parser.parse_args()
    from contextlib import ExitStack
    with ExitStack() as cleanup:
        visual=visual_server=decoder=None
        if args.visual_token_file:
            if args.display_assets is None or args.sound_root is None:parser.error('visual demo requires display-assets and sound-root')
            from .wireless_only import require_wireless_bind
            require_wireless_bind(args.bind)
            from .visual_demo import DemoState
            from .visual_server import DemoServer
            visual=DemoState()
            if args.visual_codec:
                from .visual_codec import NativeJPEG
                decoder=NativeJPEG(args.visual_codec)
            visual_server=DemoServer(visual,args.bind,token=args.visual_token_file.read_text().strip())
            cleanup.callback(visual_server.close)
        resources = open_npu() if args.backend == 'pl' else ()
        for resource in reversed(resources):cleanup.callback(resource.close)
        backend = resources[0] if resources else None
        models,model_readiness=load_enabled_models(args.models)
        nav, stopped = Navigation(), threading.Event()
        runtime = FeatureRuntime(models, backend=backend, navigation=nav)
        cleanup.callback(runtime.close)
        connection = [None]
        cleanup.callback(lambda: connection[0].close() if connection[0] is not None else None)
        pipeline=[None]
        started = time.monotonic()
        def snapshot():
            peer = connection[0]
            memory = {}
            if Path('/proc/self/status').is_file():
                memory = {key: int(value.strip().split()[0]) for key, value in
                          (line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
                          if key in ('VmRSS', 'VmSize', 'Threads')}
            return dict(schema_version=1, silent=True, actuator_control=False,
                pid=os.getpid(), memory=memory, process_cpu_seconds=time.process_time(),
                backend=backend.name if backend else 'PS_integer_reference',
                uptime_seconds=time.monotonic()-started,
                connected=peer is not None and not peer.peer.stopped.is_set(),
                page=nav.page, detail=nav.detail, results=runtime.status(),
                environment=runtime.environment_status(),
                pipeline=pipeline[0].status() if pipeline[0] else None,
                readiness=model_readiness,
                counters=runtime.counters.copy(), pending_tasks=len(runtime.pending),
                models={task: dict(version=model.version, source_kind=model.source_kind,
                         deployable=model.deployable) for task, model in models.items()},
                preview_available=args.preview is not None and preview_fresh(args.preview),
                visual=visual.snapshot() if visual else None,
                onsite_pending=['wifi_association', 'physical_keys', 'hdmi_geometry',
                    'metric_calibration', 'tablet_photos', 'z15_installation'])
        if args.display_assets is not None:
            if args.preview is None:parser.error('--display-assets requires --preview')
            from .headless_pipeline import HeadlessPipeline
            stereo=None
            if args.calibration is not None:
                from .stereo_board import BoardStereo
                stereo=BoardStereo(args.calibration,library=args.display_assets/'libz20_stereo.so')
            pipeline[0]=HeadlessPipeline(runtime,snapshot,assets=args.display_assets,preview=args.preview,
                media_root=args.media_root,sound_root=args.sound_root,hdmi=args.hdmi,keys=args.keys,
                stereo=stereo,record_pairs=args.record_pairs,visual_state=visual,visual_decoder=decoder)
            cleanup.callback(pipeline[0].close)
            pipeline[0].start()
        http = StatusHTTP((args.bind, args.http_port), snapshot, preview=args.preview,
                          analysis=(lambda:pipeline[0].audio_detail()) if pipeline[0] else None,
                          cloud=(lambda:pipeline[0].cloud_detail()) if pipeline[0] else None,
                          cloud_file=(lambda:pipeline[0].cloud_file()) if pipeline[0] else None,
                          visual_camera=pipeline[0].visual.camera_ppm if pipeline[0] and pipeline[0].visual else None)
        http_thread = threading.Thread(target=http.serve_forever, daemon=True)
        http_thread.start()
        cleanup.callback(http.server_close)
        cleanup.callback(http.shutdown)
        listener = socket.socket()
        cleanup.callback(listener.close)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((args.bind, args.port)); listener.listen(1); listener.settimeout(.01)
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, lambda *_: stopped.set())
        try:
            if visual_server:visual_server.__enter__()
            while not stopped.is_set():
                if pipeline[0]:pipeline[0].poll_keys()
                if connection[0] is None:
                    try:
                        sock, _ = listener.accept()
                    except socket.timeout:
                        continue
                    connection[0] = BoardSession(sock, runtime)
                    connection[0].start()
                try:
                    running = connection[0].pump()
                except (ValueError, AttributeError):
                    # This feature-only entry accepts no legacy mode/audio commands.
                    connection[0].close(); running = False
                if not running:
                    connection[0].close(); connection[0] = None
                stopped.wait(.01)
        finally:
            stopped.set()


if __name__ == '__main__': main()
