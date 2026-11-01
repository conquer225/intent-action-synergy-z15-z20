"""Finite private-LAN HTTP payload tests; no capture, decoding or PL access."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import time
from urllib.parse import urlparse

PAGE = r"""<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Z15 无线吞吐实测</title><style>body{font:17px system-ui;max-width:760px;margin:24px auto;padding:0 18px;line-height:1.6}button{font:inherit;padding:12px;margin:8px 8px 8px 0}pre{white-space:pre-wrap;background:#eee;padding:16px;color:#222}</style>
<h1>Z15 无线吞吐实测</h1><p>这里只传输生成的测试字节，不录屏、不读取照片，不证明视频解码或 HDMI 出画能力。使用手机热点局域网；每项约 10 秒，请保持页面前台。</p>
<button onclick="run('upload')">测手机 → Z15</button><button onclick="run('download')">测 Z15 → 手机</button><pre id="out">等待点击</pre>
<script>
let busy=false, results=[];
async function run(direction){
 if(busy)return;busy=true;document.querySelectorAll('button').forEach(x=>x.disabled=true);
 const out=document.getElementById('out');
 const block=new Uint8Array(262144);for(let i=0;i<block.length;i++)block[i]=i%251;
 let bytes=0,rounds=0,errors=0,times=[],start=performance.now();out.textContent='测试中，保持页面前台…';
 try{while(performance.now()-start<10000){let a=performance.now();const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),5000);try{let r=await fetch('/'+direction,{method:direction==='upload'?'POST':'GET',body:direction==='upload'?block:undefined,cache:'no-store',signal:controller.signal});if(!r.ok)throw Error('HTTP '+r.status);if(direction==='upload'){let ack=await r.json();if(ack.bytes!==block.length)throw Error('长度不符');bytes+=ack.bytes;}else{let b=await r.arrayBuffer();if(b.byteLength!==block.length)throw Error('长度不符');bytes+=b.byteLength;}}finally{clearTimeout(timer);}times.push(performance.now()-a);rounds++;}
 }catch(e){errors++;out.textContent='发生错误：'+String(e)+'\n';}
 let elapsed=(performance.now()-start)/1000;times.sort((a,b)=>a-b);let result={source:'手机浏览器',direction,bytes,elapsed_s:elapsed,mbps:bytes*8/elapsed/1000000,rounds,errors,chunk_p95_ms:times.length?times[Math.min(times.length-1,Math.floor(times.length*.95))]:null,visibility:document.visibilityState};
 results.push(result);out.textContent=JSON.stringify(results,null,2);try{const saved=await fetch('/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(result)});if(!saved.ok)throw Error('HTTP '+saved.status);out.textContent+='\n结果已回传。';}catch(e){out.textContent+='\n结果未能回传，请截图保存：'+String(e);}
 busy=false;document.querySelectorAll('button').forEach(x=>x.disabled=false);
}
</script></html>"""
BLOCK = (bytes(range(251)) * 1045)[:262144]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(6)
        self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def log_message(self, *_):
        pass

    def reply(self, data, content_type="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self.reply(PAGE.encode(), "text/html; charset=utf-8")
        elif path == "/download":
            self.reply(BLOCK, "application/octet-stream")
        elif path == "/health":
            self.reply(b'{"test_only":true}')
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not 1 <= length <= 1048576 or self.path not in {"/upload", "/result"}:
            self.send_error(400)
            self.close_connection = True
            return
        data = self.rfile.read(length)
        if len(data) != length:
            self.close_connection = True
            return
        if self.path == "/result":
            result = json.loads(data)
            print(json.dumps({"browser_result": result, "peer": self.client_address[0],
                              "received_unix_s": time.time()}, ensure_ascii=False), flush=True)
        self.reply(json.dumps({"bytes": len(data)}).encode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", required=True)
    parser.add_argument("--port", type=int, default=9118)
    args = parser.parse_args()
    with ThreadingHTTPServer((args.bind, args.port), Handler) as server:
        print("PRIVATE_NETWORK_TEST_READY", flush=True)
        server.serve_forever(poll_interval=.5)
