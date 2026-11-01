"""Private phone media entry; never edits formal services, only finite candidate sessions."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import uuid
import time
import sys
from urllib.parse import urlsplit,parse_qs

from chunk_cache import manifest
from upload_server import Handler, Store, make_server, write_json
from prewear import hdmi_preflight

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'system_runtime'))
sys.path.insert(0,str(BASE/'system_runtime/wheelchair_ssvep'))
sys.path.append('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
from wheelchair_link import launch as launch_wheelchair, read_status as wheelchair_status, PHONE_LEASE_SECONDS
from bench_network_bridge import DIRECTIONS
PYTHON='/usr/local/share/pynq-venv/bin/python3'


def run(*args):
    return subprocess.run(args,capture_output=True,text=True,check=True,timeout=20).stdout.strip()


def eye_device(root=Path('/sys/bus/usb/devices')):
    if root.is_dir():
        for device in root.iterdir():
            try:
                if ((device/'idVendor').read_text().strip()!='2104'
                        or (device/'serial').read_text().strip()!='CN033F74DTOB186P0822A00'):continue
                pid=(device/'idProduct').read_text().strip()
            except FileNotFoundError:
                continue
            return dict(state='runtime' if pid=='0124' else 'maintenance' if pid=='0102' else 'unsupported',pid=pid)
    return dict(state='missing',pid=None)


class Controller:
    def __init__(self,state):
        self.state=state
        self.lock=threading.Lock()
        self.wheelchair_lock=threading.Lock()
        self.wheelchair_epoch=uuid.uuid4().hex
        self.job=None
        self.session=None
        self.store=None
        from guardianloop_system.media_library import MediaLibrary
        from guardianloop_system.live_inputs import BrainInputs
        self.library=MediaLibrary(BASE/'ratings.json');self.brain=BrainInputs()
        from wear_session import WearSession
        self.wear=WearSession()

    def wearing(self, action, value):
        if action=='wear_continue':
            return dict(state='unchanged',wear=self.wear.snapshot(),reason='继续当前佩戴；未清除校准基线')
        if not isinstance(value,dict) or set(value)!={'confirm','expected_id'} or value['confirm'] is not True:
            raise ValueError('开始新佩戴将清除旧基线，必须主动确认')
        if self.active():
            self.command('force_stop')
        return self.wear.request_new(value['expected_id'])

    def videos(self):
        rows=[]
        for ident,name in (('sd01','小奶猫（SD竖版）'),('sd02','小狗（SD竖版）')):
            root=BASE/'assets'/ident
            if (root/'ready.json').is_file():rows.append(dict(id=ident,name=name,source='SD_card',
                cache=str(root/'cache'),download=str(root/'portrait.mp4')))
        for item in self.store.items():
            if item.get('integrity')!='passed':continue
            rows.append(dict(id=item['id'],name=item['name'],source='phone_upload',
                cache=str(BASE/'assets'/item['id']/'cache'),download=str(self.store.root/(item['id']+'.mp4'))))
        self.library.replace(rows);return rows

    def active(self):
        if self.session is None:
            # A web restart must retain control of this exact already-running player.
            path=BASE/'player_status.json'
            row=json.loads(path.read_text()) if path.is_file() else {}
            ident=row.get('session_id','')
            if not re.fullmatch('play-[a-f0-9]{8}',ident):return False
            config=BASE/(ident+'.json')
            if not config.is_file():return False
            candidate=json.loads(config.read_text())
            if (candidate.get('remote')!=str(BASE) or candidate.get('session_id')!=ident
                    or candidate.get('hardware_unit')!=ident+'.service'
                    or candidate.get('hardware_hashes')!=self.state.get('hardware_hashes')):
                raise ValueError('Display ownership differs; refuse session adoption')
            self.session=candidate
        fields=run('systemctl','show',self.session['hardware_unit'],'-p','MainPID','--value')
        return int(fields or '0')>0

    def cache(self,identifier):
        if identifier=='fixture60compact':return BASE/'fixture60compact'
        if identifier=='fixture60yuv':return BASE/'fixture60'
        if identifier=='fixture60':return BASE/'fixture60compact'
        if identifier=='fixture60preview':return BASE/'fixture60preview'
        if not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('Invalid media ID')
        if not any(item['id']==identifier and item.get('integrity')=='passed' for item in self.store.items()):
            raise ValueError('Upload has not passed integrity checks')
        if not (BASE/'assets'/identifier/'ready.json').is_file():
            raise ValueError('Prepare this video first')
        return BASE/'assets'/identifier/'cache'

    def prepare(self,identifier):
        if not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('Invalid upload ID')
        if not any(item['id']==identifier and item.get('integrity')=='passed' for item in self.store.items()):
            raise ValueError('Verified upload not found')
        target=BASE/'assets'/identifier
        if target.exists():raise ValueError('Preparation already exists; retained failures require inspection')
        if self.active() or (self.job and self.job.is_alive()):raise ValueError('Wait for playback/preparation to finish')
        if shutil.disk_usage(BASE).free<5*1024**3:raise ValueError('Insufficient reserve space for preparing cache')
        self.job=threading.Thread(target=self._prepare,args=(identifier,target),daemon=True)
        self.job.start()
        return {'state':'preparing','id':identifier,'silent':True}

    def _prepare(self,identifier,target):
        write_json(BASE/'preparation_status.json',{'state':'preparing','id':identifier})
        log=BASE/(identifier+'-prepare.log')
        try:
            with log.open('w') as output:
                subprocess.run([PYTHON,str(BASE/'prepare_asset.py'),'--source',
                    str(self.store.root/(identifier+'.mp4')),'--output',str(target)],
                    stdout=output,stderr=output,check=True,timeout=2700)
        except (OSError,subprocess.SubprocessError):
            write_json(BASE/'preparation_status.json',{'state':'failed','id':identifier,
                'error':'准备未通过，原文件和诊断文件保留；需要检查，未发布播放缓存。'})
        else:write_json(BASE/'preparation_status.json',{'state':'ready','id':identifier})

    def start_home(self):
        if self.active():return self.command('home')
        return self.play('sd02', initial_page='home')

    def play(self,identifier,initial_page='video'):
        if initial_page not in ('home','video'):raise ValueError('Invalid initial display page')
        if self.active() or (self.job and self.job.is_alive()):raise ValueError('Another media operation is running')
        candidate=[]
        if self.state.get('hdmi_candidate') is True:
            if not all(self.state.get(key) for key in ('ssvep_runtime','native_scan_library','native_scan_sha256')):
                raise ValueError('Native HDMI candidate is not prepared')
            candidate=['--hdmi-candidate','--ssvep-runtime',self.state['ssvep_runtime'],
                       '--ssvep-port',str(self.state.get('ssvep_port',9105)),
                       '--native-scan-library',self.state['native_scan_library'],
                       '--native-scan-sha256',self.state['native_scan_sha256']]
        rows=self.videos();ready={row['id'] for row in self.library.snapshot() if row['prepared']}
        prepared=[row for row in rows if row['id'] in ready]
        selected=next((row for row in prepared if row['id']==identifier),None)
        if selected is None:raise ValueError('Prepare this video before HDMI playback')
        cache=Path(selected['cache']);meta=manifest(cache)
        if (meta['width'],meta['height'])!=(288,512):raise ValueError('This candidate requires a prepared portrait canvas')
        ident='play-'+uuid.uuid4().hex[:8]
        config=dict(self.state,cache=str(cache),session_id=ident,owner_script='media_player.py',
                    hardware_unit=ident+'.service',eye_diagnostic=False,unified_system=True,live_system=True,
                    playlist=prepared,video_index=prepared.index(selected),initial_page=initial_page,
                    seconds=None if self.state.get('user_controlled') is True else min(600,int(self.state.get('test_seconds',600))))
        session=BASE/(ident+'.json')
        write_json(session,config)
        write_json(BASE/'player_status.json',{'state':'starting','session_id':ident,'silent':True})
        if self.state.get('user_controlled') is not True:
            run('systemd-run','--unit='+ident+'-restore','--on-active=650s','--timer-property=AccuracySec=1s',
                'env','XILINX_XRT=/usr',PYTHON,str(BASE/'playback_recovery.py'),'--state',str(session))
        try:
            run('systemd-run','--unit='+ident,'--property=TimeoutStopSec=infinity',
                '--property=KillMode=process','--property=LimitCORE=0','--property=Nice=5','env','XILINX_XRT=/usr','OPENBLAS_NUM_THREADS=1',
                PYTHON,str(BASE/'media_player.py'),'--state',str(session),*candidate)
        except subprocess.SubprocessError:
            # Keep the timer armed if a launch acknowledgement is ambiguous.
            raise ValueError('Player launch did not acknowledge; recovery timer retained')
        self.session=config
        return {'state':'starting','session_id':ident,'silent':True}

    def command(self,action,value=None):
        if action=='force_stop' and self.state.get('wheelchair_link') is True:
            with self.wheelchair_lock:self.manual_wheelchair('stop')
        if not self.active():raise ValueError('No active player session')
        if action=='eye_start':
            device=eye_device()
            if device['state']=='maintenance':raise ValueError('眼控停在维护模式 0102，不能采样或标定；需先恢复设备运行模式')
            if device['state']!='runtime':raise ValueError('未识别到正常眼控运行设备 0124，请检查眼控 USB')
        if action=='hdmi_start':
            snapshot=self.snapshot();system=snapshot['player'].get('system') or {}
            gate=snapshot['hdmi_preflight']
            if not gate['ready']:raise ValueError(gate['reason'])
            if isinstance(value,dict) and value.get('record') is True and not gate['raw_recording_supported']:
                raise ValueError('当前采集不支持同步原始录制，未启动')
        lane='stop' if action=='force_stop' else 'command'
        path=Path('/dev/shm')/(BASE.name+'-player-'+lane+'.json')
        identifier=uuid.uuid4().hex
        write_json(path,{'session_id':self.session['session_id'],'id':identifier,'action':action,
                        'value':value,'queued_monotonic':time.monotonic()})
        return {'queued':action,'command_id':identifier,'not_yet_confirmed':True,'silent':True}

    def manual_wheelchair(self,value):
        remote=self.state.get('wheelchair_motor_test') is True
        if isinstance(value,dict):
            if (not remote or set(value)!={'direction','epoch'}
                    or value['epoch']!=self.wheelchair_epoch):
                raise ValueError('遥控页面已过期，请刷新后重新选择方向')
            value=value['direction']
        elif remote and value not in ('stop','ssvep'):
            raise ValueError('持续遥控需要当前页面令牌，请刷新手机页面')
        if type(value) is not str or value not in DIRECTIONS|{'ssvep'}:
            raise ValueError('Invalid wheelchair direction')
        if self.state.get('wheelchair_link') is not True:raise ValueError('轮椅发送接口未启动')
        identifier=uuid.uuid4().hex
        row=dict(id=identifier,value=value,boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                 queued_monotonic=time.monotonic())
        if remote:
            row['heartbeat_monotonic']=row['queued_monotonic']
            row['heartbeat_confirmed']=False
            self.wheelchair_epoch=uuid.uuid4().hex
        write_json(Path('/dev/shm')/(BASE.name+'-wheelchair-manual.json'),row)
        return dict(queued='wheelchair_manual',command_id=identifier,not_yet_confirmed=True,
                    physical_output_enabled=remote,control_epoch=self.wheelchair_epoch if remote else None)

    def wheelchair_heartbeat(self,value):
        if self.state.get('wheelchair_motor_test') is not True or not isinstance(value,str):
            raise ValueError('Invalid manual heartbeat')
        path=Path('/dev/shm')/(BASE.name+'-wheelchair-manual.json')
        row=json.loads(path.read_text());now=time.monotonic()
        if (row.get('id')!=value or row.get('value') not in DIRECTIONS-{'stop'}
                or not 0<=now-row.get('heartbeat_monotonic',0)<=PHONE_LEASE_SECONDS):
            raise ValueError('遥控已停止或心跳过期，请重新点方向；不会自动恢复')
        row['heartbeat_monotonic']=now;row['heartbeat_confirmed']=True;write_json(path,row)
        return dict(heartbeat=True,command_id=value)

    def snapshot(self):
        def read(name):
            path=BASE/name
            return json.loads(path.read_text()) if path.exists() else {}
        items=[]
        for item in self.store.items():
            ready=BASE/'assets'/item['id']/'ready.json'
            items.append({'id':item['id'],'name':item['name'],'bytes':item['bytes'],
                          'verified':item.get('integrity')=='passed','prepared':ready.is_file()})
        self.videos()
        ram=Path('/dev/shm')/(BASE.name+'-player-status.json')
        player=json.loads(ram.read_text()) if ram.is_file() else read('player_status.json')
        if not 0<=time.monotonic()-player.get('updated_monotonic',0)<=2:
            player=dict(state='inactive',system=None,physical_control=False)
            ident=read('player_status.json').get('session_id','')
            if re.fullmatch('play-[a-f0-9]{8}',ident):
                report=read(ident+'-report.json')
                if report.get('errors'):
                    player.update(state='error',error=str(report['errors'][-1])[:300])
        brain=self.brain.snapshot(time.monotonic())
        return {'files':items,'player':player,'videos':self.library.snapshot(),
                'brain':brain,'favorites_storage':'board_originals_and_ratings',
                'wear':self.wear.snapshot(),
                'wheelchair':wheelchair_status(Path('/dev/shm')/(BASE.name+'-wheelchair-link.json'),time.monotonic(),
                                              motor_test=self.state.get('wheelchair_motor_test') is True),
                'wheelchair_control_epoch':self.wheelchair_epoch,
                'hdmi_preflight':hdmi_preflight(player.get('system') or {},brain.get('ssvep_hdmi') or {},
                                               available=self.state.get('hdmi_candidate') is True),
                'phone_file_saved':False,
                'preparation':read('preparation_status.json'),'silent':player.get('silent',True),
                'audio_output':player.get('audio_output',False),
                'fixture_ready':(BASE/'fixture60compact'/'manifest.json').is_file(),
                'multitask_16fps_qualified':False,
                'hdmi_candidate_available':self.state.get('hdmi_candidate') is True and
                    all(self.state.get(key) for key in ('ssvep_runtime','native_scan_library','native_scan_sha256')),
                'preview_fixture_ready':(BASE/'fixture60preview'/'manifest.json').is_file(),
                'user_controlled':self.state.get('user_controlled') is True,
                'auto_hdmi_on_drive':self.state.get('auto_hdmi_on_drive') is True,
                'eye_device':eye_device(),
                'scope':'user-controlled session; no automatic expiry; no boot changes' if self.state.get('user_controlled') is True else 'temporary isolated entry; playback capped at 600 seconds; no permanent install'}


class MediaStore(Store):
    def decode(self,item):
        # Upload verification and expensive preparation are separate explicit actions.
        item['decode_state']='stored'
        with self.state_lock:write_json(self.root/(item['id']+'.json'),item)


class MediaHandler(Handler):
    def do_GET(self):
        parts=urlsplit(self.path)
        if parts.path.startswith('/download/'):
            return self.download(parts)
        if self.path in ('/','/player','/system'):
            self.reply(200,(BASE/'system_mobile.html').read_bytes(),'text/html; charset=utf-8')
        elif self.path=='/system_mobile.js':
            self.reply(200,(BASE/'system_mobile.js').read_bytes(),'text/javascript; charset=utf-8')
        elif self.path=='/api/player' and self.authorized():
            with self.server.controller.lock:self.reply(200,self.server.controller.snapshot())
        elif self.path!='/api/player':super().do_GET()

    def do_POST(self):
        if self.path!='/api/player':return super().do_POST()
        length=self.headers.get('Content-Length','')
        if self.headers.get('Transfer-Encoding') or not length.isdecimal() or not 1<=int(length)<=2048:
            return self.reject(400,'控制请求长度无效。')
        body=self.rfile.read(int(length))
        if len(body)!=int(length):return self.reject(400,'控制请求不完整。')
        # Drain the bounded body before rejecting; unread POST bytes can reset Windows sockets.
        if not self.authorized():return
        try:
            data=json.loads(body)
            if not isinstance(data,dict) or set(data)-{'action','id','value'}:raise ValueError('Invalid control fields')
            action=data.get('action')
            if action in ('wheelchair_manual','wheelchair_heartbeat'):
                with self.server.controller.wheelchair_lock:
                    result=(self.server.controller.manual_wheelchair(data.get('value')) if action=='wheelchair_manual'
                            else self.server.controller.wheelchair_heartbeat(data.get('value')))
                return self.reply(202,result)
            with self.server.controller.lock:
                if action=='prepare':result=self.server.controller.prepare(data.get('id',''))
                elif action in ('wear_continue','wear_new'):result=self.server.controller.wearing(action,data.get('value'))
                elif action=='play':result=self.server.controller.play(data.get('id',''))
                elif action=='display_start':result=self.server.controller.start_home()
                elif action in ('pause','resume','stop'):result=self.server.controller.command(action)
                elif action=='volume':
                    value=data.get('value')
                    if type(value) is not int or not 0<=value<=100:raise ValueError('音量必须为0到100的整数')
                    if not self.server.controller.state.get('hdmi_audio'):raise ValueError('此会话未启用HDMI音频')
                    result=self.server.controller.command('volume',value)
                elif action in ('home','arm','eye_start','eye_stop','force_stop','fatigue_warning'):
                    result=self.server.controller.command(action)
                elif action in ('hdmi_start','hdmi_stop'):
                    if self.server.controller.state.get('hdmi_candidate') is not True:
                        raise ValueError('HDMI 刺激候选尚未部署；未启动')
                    if action=='hdmi_start':
                        value=data.get('value')
                        if value is not True and not (isinstance(value,dict) and
                                set(value)=={'consent','record'} and value['consent'] is True
                                and type(value['record']) is bool):
                            raise ValueError('请先主动确认闪烁测试及录制选择；未启动')
                    result=self.server.controller.command(action,data.get('value'))
                elif action=='choose':
                    if type(data.get('value')) is not int or not 0<=data['value']<=2:raise ValueError('Invalid choice')
                    result=self.server.controller.command(action,data['value'])
                elif action=='ack':
                    if data.get('value') not in ('mood','fatigue'):raise ValueError('Invalid alert')
                    result=self.server.controller.command(action,data['value'])
                elif action=='video':
                    if not any(row['id']==data.get('id') and row['prepared'] for row in self.server.controller.library.snapshot()):
                        raise ValueError('Video is not prepared')
                    result=self.server.controller.command('video',data['id'])
                elif action=='rate':
                    self.server.controller.library.rate(data.get('id'),data.get('value'))
                    result={'rating_saved':True,'phone_file_saved':False}
                else:raise ValueError('Unknown control action')
        except (ValueError,TypeError,OSError,subprocess.SubprocessError) as error:
            return self.reject(409,str(error))
        self.reply(202,result)

    def download(self,parts):
        identifier=parts.path[len('/download/'):]
        # Single-use authenticated browser fetch uses a header, never a query-string secret.
        if not self.authorized():return
        if parse_qs(parts.query):return self.reject(400,'下载链接参数无效')
        with self.server.controller.lock:
            video=next((row for row in self.server.controller.videos() if row['id']==identifier),None)
        if video is None:return self.reject(404,'视频不存在')
        path=Path(video['download'])
        if not path.is_file():return self.reject(404,'下载文件尚未准备好')
        size=path.stat().st_size
        if size>512*1024**2:return self.reject(413,'手机端下载限制512MB')
        self.send_response(200);self.send_header('Content-Type','video/mp4')
        self.send_header('Content-Length',str(size));self.send_header('Cache-Control','no-store')
        self.send_header('Content-Disposition','attachment; filename="'+identifier+'.mp4"')
        self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
        try:
            with path.open('rb') as handle:
                for chunk in iter(lambda:handle.read(262144),b''):self.wfile.write(chunk)
        except (BrokenPipeError,ConnectionResetError,TimeoutError):self.close_connection=True


def main():
    os.umask(0o077)
    p=argparse.ArgumentParser();p.add_argument('--key-file',type=Path,required=True)
    p.add_argument('--port',type=int,default=9117)
    args=p.parse_args();state=json.loads((BASE/'media_state.json').read_text())
    if not 1024<=args.port<=65535:raise ValueError('Invalid private media port')
    (BASE/'assets').mkdir(mode=0o700,exist_ok=True)
    store=MediaStore(state['uploaded_root'],args.key_file.read_text().strip(),'unused')
    controller=Controller(state);controller.store=store
    server=make_server('0.0.0.0',args.port,store);server.RequestHandlerClass=MediaHandler
    server.controller=controller
    link=launch_wheelchair(BASE,PYTHON,motor_test=state.get('wheelchair_motor_test') is True) if state.get('wheelchair_link') is True else None
    try:
        with server:server.serve_forever(poll_interval=.5)
    finally:
        controller.brain.close()
        if link:
            link.terminate()
            try:link.wait(timeout=3)
            except subprocess.TimeoutExpired:link.kill();link.wait(timeout=2)


if __name__=='__main__':main()
