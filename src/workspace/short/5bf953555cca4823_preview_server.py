"""Loopback-only, authenticated manual prototype. No board or actuator traffic."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import secrets
import time

from guardianloop_system.core import SystemController
from wheelchair_ssvep.dry_run_bridge import demo_snapshot


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(3)

    def log_message(self,*_):pass

    def reply(self,code,data,content_type='application/json; charset=utf-8'):
        body=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
        self.send_response(code);self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)

    def authorized(self):
        origin=self.headers.get('Origin')
        expected='http://127.0.0.1:'+str(self.server.server_port)
        return (self.headers.get('Host')=='127.0.0.1:'+str(self.server.server_port) and
            origin in (None,expected) and secrets.compare_digest(self.headers.get('X-Preview-Key',''),self.server.key))

    def do_GET(self):
        if self.path=='/':self.reply(200,Path(__file__).with_name('preview.html').read_bytes(),'text/html; charset=utf-8')
        elif self.path=='/api/state':
            if not self.authorized():self.reply(403,{'error':'仅限本机授权预览'});return
            self.reply(200,self.server.system.snapshot(time.monotonic()))
        else:self.reply(404,{'error':'Not found'})

    def do_POST(self):
        if self.path!='/api/action':self.reply(404,{'error':'Not found'});return
        length=self.headers.get('Content-Length','')
        if self.headers.get('Transfer-Encoding') or not length.isdecimal() or not 1<=int(length)<=1024:
            self.reply(400,{'error':'Invalid length'});return
        # Consume the bounded body before closing a rejected Windows connection.
        # Otherwise unread bytes can reset the socket before the 403 is received.
        try:body=self.rfile.read(int(length))
        except TimeoutError:self.reply(408,{'error':'Request timeout'});return
        if len(body)!=int(length):self.reply(400,{'error':'Incomplete body'});return
        if not self.authorized():self.reply(403,{'error':'仅限本机授权预览'});return
        try:
            data=json.loads(body)
            if not isinstance(data,dict) or set(data)-{'action','value'}:raise ValueError('Invalid fields')
            action=data.get('action');value=data.get('value');now=time.monotonic();system=self.server.system
            if action=='presented':system.presented(value,now)
            elif action=='choose':system.choose(value,now)
            elif action=='arm':system.arm_virtual_direction(now)
            elif action=='ssvep':
                if type(value) is not int or value not in (8,10,12,14):raise ValueError('Invalid frequency')
                self.server.window+=50
                system.ssvep(demo_snapshot(value,self.server.window),now)
            elif action=='lost':system.signal_lost(now)
            elif action=='mi':
                if value not in ('right','left','neutral'):raise ValueError('Invalid MI label')
                self.server.mi_index+=1;n=self.server.mi_index
                system.mi(dict(id='manual-'+str(n),session='manual-prototype',label=value,
                    received_at=now,window_start=n*500,window_end=(n+1)*500,
                    accepted=True,quality_ready=True),now)
            elif action=='mood':system.monitor('emotion','poor',now,source='user_report',qualified=True)
            elif action=='gameemo':system.monitor('emotion','boring',now,source='GAMEEMO_condition',qualified=True)
            elif action=='fatigue':system.monitor('fatigue','severe_candidate',now,source='manual_test',qualified=True)
            elif action=='ack':
                if value not in ('mood','fatigue'):raise ValueError('Unknown alert')
                system.acknowledge_alert(value,now)
            else:raise ValueError('Unknown action')
        except (ValueError,TypeError) as error:self.reply(400,{'error':str(error)});return
        self.reply(200,system.snapshot(now))


def make_server(port=0,key=None):
    server=HTTPServer(('127.0.0.1',port),Handler)
    server.key=key or secrets.token_hex(16);server.system=SystemController(time.monotonic())
    server.system.video_count=10;server.system.song_count=10
    server.window=1000;server.mi_index=0
    return server


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=9120)
    parser.add_argument('--seconds',type=int,default=1800);args=parser.parse_args()
    if not 1<=args.seconds<=3600:raise ValueError('Preview capped at one hour')
    server=make_server(args.port);server.timeout=.5
    print('LOCAL_MANUAL_PREVIEW http://127.0.0.1:'+str(server.server_port)+'/#'+server.key,flush=True)
    deadline=time.monotonic()+args.seconds
    try:
        while time.monotonic()<deadline:server.handle_request()
    finally:server.server_close()


if __name__=='__main__':main()
