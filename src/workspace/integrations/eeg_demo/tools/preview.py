"""Local offline preview. No synthetic EEG or hardware connections are created."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class Preview(BaseHTTPRequestHandler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        names={'/':'eeg_demo.html','/eeg-demo':'eeg_demo.html','/eeg-demo/':'eeg_demo.html',
               '/eeg_demo.css':'eeg_demo.css','/eeg_demo.js':'eeg_demo.js','/eeg_demo_core.js':'eeg_demo_core.js'}
        if path=='/api/eeg-demo':
            body=json.dumps(dict(format='guardianloop-eeg-live-v1',origin='live',stale=True,
                            reason='本地预览 · 未连接脑电设备',status={},telemetry={},control_enabled=False),ensure_ascii=False).encode()
            kind='application/json; charset=utf-8'
        elif path in names:
            name=names[path];body=(ROOT/'web'/name).read_bytes()
            kind=('text/css' if name.endswith('.css') else 'text/javascript' if name.endswith('.js') else 'text/html')+'; charset=utf-8'
        else:self.send_error(404);return
        self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def log_message(self,*_):pass


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=9128);args=parser.parse_args()
    print('Local preview: http://127.0.0.1:%d/eeg-demo (no hardware)'%args.port,flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Preview).serve_forever()
