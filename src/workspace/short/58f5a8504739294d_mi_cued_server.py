"""Standalone local MI candidate page; no acquisition or official service changes."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mi_cued import CuedMISession
from mi_eegnet_portable import OfflineEEGNet

PAGE_PATH = Path(__file__).with_name('mi_cued.html')


MULTITASK_PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>五任务隔离候选</title><main><h1>五任务隔离候选入口</h1>
<p>回放／实验来源见状态。不是新的佩戴数据，不验证识别准确率，永不控制外设。</p>
<p><a href="/mi-cued">打开左右手运动想象有提示候选</a></p>
<p>情绪、疲劳、SEED、SSVEP复用同一主循环输入；正式9102不受此页替换。</p>
<pre id="status">读取中</pre></main><script>
async function refresh(){try{let r=await fetch('/api/multitask',{cache:'no-store'});
if(!r.ok)throw Error('HTTP');document.getElementById('status').textContent=JSON.stringify(await r.json(),null,2);
}catch(e){document.getElementById('status').textContent='连接中断，不能使用旧结果';}}
refresh();setInterval(refresh,1000);</script></html>'''.encode('utf-8')


def make_handler(session, multitask=None):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, payload, content_type='application/json; charset=utf-8'):
            body = (json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
                    if content_type.startswith('application/json') else payload)
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/' and multitask is not None:
                self.reply(200, MULTITASK_PAGE, 'text/html; charset=utf-8')
            elif self.path in ('/', '/mi-cued'):
                self.reply(200, PAGE_PATH.read_bytes(), 'text/html; charset=utf-8')
            elif self.path == '/api/mi-cue':
                self.reply(200, session.snapshot())
            elif self.path == '/api/multitask' and multitask is not None:
                self.reply(200, dict(multitask(), mi=session.snapshot()))
            else:
                self.reply(404, {'error': 'Unknown endpoint'})

        def do_POST(self):
            if self.path != '/api/mi-cue':
                self.reply(404, {'error': 'Unknown endpoint'}); return
            if self.headers.get('Origin') != 'http://' + self.headers.get('Host', ''):
                self.reply(403, {'error': 'Same-origin request required'}); return
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.reply(415, {'error': 'JSON object required'}); return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    raise ValueError('Body must be 1..4096 bytes')
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise ValueError('JSON object required')
                self.reply(200, session.command(request))
            except (ValueError, TypeError) as error:
                self.reply(400, {'error': str(error)})
            except OSError as error:
                self.reply(500, {'error': str(error)})

        def log_message(self, *args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=9104)
    parser.add_argument('--experimental-model', type=Path)
    parser.add_argument('--allow-experimental', action='store_true')
    parser.add_argument('--source', choices=('live', 'replay'), default='live')
    parser.add_argument('--audit-log', type=Path)
    args = parser.parse_args()
    if args.allow_experimental != bool(args.experimental_model):
        parser.error('Both --experimental-model and --allow-experimental are required together')
    model = OfflineEEGNet(args.experimental_model, allow_experimental=True) if args.experimental_model else None
    session = CuedMISession(model, source=args.source, log_path=args.audit_log)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(session))
    print(f'MI_LOCAL_CANDIDATE: http://{args.host}:{args.port}/mi-cued; no acquisition adapter attached', flush=True)
    try:
        server.serve_forever()
    finally:
        session.disconnect('server_shutdown')
        server.server_close()


if __name__ == '__main__':
    main()
