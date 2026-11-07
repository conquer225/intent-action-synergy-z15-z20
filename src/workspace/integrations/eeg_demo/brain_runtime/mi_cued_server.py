"""Standalone local MI candidate page; no acquisition or official service changes."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mi_cued import CuedMISession
from mi_eegnet_portable import OfflineEEGNet

PAGE_PATH = Path(__file__).with_name('mi_cued.html')


MULTITASK_PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>意动协同 · 脑电分析</title>
<style>:root{font-family:"Microsoft YaHei",sans-serif;color:#332c22;background:#fbf7ee;line-height:1.45}
body{margin:0}main{max-width:900px;margin:auto;padding:24px}h1{font-size:26px;font-weight:500}
h2{font-size:20px;font-weight:500;margin-top:32px}a{color:#855f22;text-underline-offset:4px}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:12px 8px;border-bottom:1px solid #d9ccb6}
th{font-weight:500}td{font-variant-numeric:tabular-nums;overflow-wrap:anywhere}#label{font-size:30px;color:#855f22}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}summary{cursor:pointer;padding:12px 0}
::selection{background:#f2e8d3}a:focus-visible,summary:focus-visible{outline:2px solid #855f22;outline-offset:4px}</style>
<main><h1>意动协同 · 脑电分析与运动想象</h1>
<p><a href="/mi-cued">进入左右手提示试次与虚拟手</a></p>
<h2>Z15 PL · 滤波器组 / CSP / SVM</h2><p id="label" role="status">等待脑电窗口</p>
<table><tbody><tr><th>输入</th><td>8 通道 · 250 Hz</td></tr>
<tr><th>窗口 / 样本计数</th><td id="counts">—</td></tr><tr><th>六项 Q12 特征</th><td id="features">—</td></tr>
<tr><th>SVM Q24 分数</th><td id="score">—</td></tr><tr><th>模型 SHA256</th><td id="model">—</td></tr>
<tr><th>本次调用耗时</th><td id="timing">—</td></tr></tbody></table>
<details><summary>查看各分析任务的状态与数据来源</summary><pre id="status">读取中</pre></details></main><script>
const put=(id,value)=>document.getElementById(id).textContent=value;
function render(data){const task=data.tasks?.pl_mi,p=task?.stale?{}:(task?.payload||{});
put('label',p.valid?({left:'左手运动想象',right:'右手运动想象'}[p.label]||p.label):
({signal_clipping:'信号饱和，重新收集窗口',backend_unavailable:'PL 服务连接中',stale_input:'等待新鲜脑电',
prediction:'窗口已完成'}[p.reason]||'正在收集脑电窗口'));
put('counts',p.window_count==null?'—':p.window_count+' / '+p.sample_count);
put('features',p.features?.join(' · ')||'—');put('score',p.score_q24??'—');put('model',p.model_sha256||'—');
put('timing',p.timing?((p.timing.total_seconds*1000).toFixed(3)+' ms · PS 调用及结果读取'):'—');
put('status',JSON.stringify(data,null,2));}
async function refresh(){try{let r=await fetch('/api/multitask',{cache:'no-store'});
if(!r.ok)throw Error('HTTP');render(await r.json());
}catch(e){render({});put('label','连接中断，正在重连');put('status','正在重新连接脑电服务');}}
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
