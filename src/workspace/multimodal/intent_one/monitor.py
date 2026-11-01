"""Read-only telemetry adapters; acquisition and actuator ownership stay upstream."""
import json,socket,threading,time
from collections import deque
from urllib.request import build_opener,ProxyHandler,Request
from .telemetry import strict_object,integer
from .reference import WindowStatistics

class PendulumReader:
    def __init__(self,peer):self.peer=peer;self.session=self.seq=self.last=None
    def feed(self,data,peer,now):
        if peer!=self.peer or len(data)>512:return None
        try:row=json.loads(data.decode('utf8'),object_pairs_hook=strict_object)
        except (ValueError,UnicodeError):return None
        if not isinstance(row,dict) or row.get('v')!=1 or row.get('type')!='stm_raw':return None
        for key,lo,hi in [('session',0,2**32-1),('seq',0,2**32-1),('received_ms',0,2**32-1),('time_ms',0,2**32-1),('adc',0,4095),('location',-32768,32767),('pwm',-100,100)]:
            if not integer(row.get(key),lo,hi):return None
        if self.session==row['session'] and self.seq is not None and not 0<(row['seq']-self.seq)&0xffffffff<0x80000000:return None
        self.session=row['session'];self.seq=row['seq'];self.last=dict(row,received_at=now,clock='stm_boot_ms');return self.last
    def snapshot(self,now):return self.last if self.last and 0<=now-self.last['received_at']<=.6 else None

class PendulumConnection:
    def __init__(self,peer='192.168.4.1'):
        self.reader=PendulumReader(peer);self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.sock.bind(('',9011));self.sock.setblocking(False)
    def poll(self,now):
        for _ in range(8):
            try:data,peer=self.sock.recvfrom(513)
            except BlockingIOError:break
            self.reader.feed(data,peer[0],now)
        return self.reader.snapshot(now)
    def close(self):self.sock.close()

class ProcessModel:
    def __init__(self):
        self.raw=deque(maxlen=500);self.statistics=WindowStatistics();self.rms=None;self.pressed=None;self.events=deque(maxlen=128)
    def observe(self,row):
        if row['type']=='raw':
            if row['discontinuity']:self.statistics.reset();self.rms=None;self.raw.clear()
            if row['valid']:
                self.raw.extend(row['samples'])
                for answer in self.statistics.process(row['samples']):self.rms=round(answer['rms'],2)
        elif row['type'] in ('contact','signal_status'):
            self.pressed=row.get('pressed') if row.get('valid',True) else None
            if row['type']=='contact':self.events.append('S3电极'+('按下' if row['pressed'] else '松开')+'；事件 '+str(row['event_id']))
    def expire(self):self.statistics.reset();self.rms=None;self.pressed=None

class BrainApi:
    def __init__(self,url='http://127.0.0.1:9102/api/',start=True):
        self.url=url;self.rows={};self.lock=threading.Lock();self.stop=threading.Event()
        self.opener=build_opener(ProxyHandler({}));self.thread=None
        if start:self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()
    def _run(self):
        while not self.stop.is_set():
            for endpoint in ('ssvep-shadow','status','telemetry','mi-cue'):
                try:
                    with self.opener.open(self.url+endpoint,timeout=.25) as response:data=response.read(65537)
                    if len(data)>65536:raise ValueError('oversize brain status')
                    row=json.loads(data);error=None
                    if not isinstance(row,dict):raise ValueError('non-object brain status')
                except (OSError,ValueError,TimeoutError) as exc:row={};error=type(exc).__name__
                with self.lock:self.rows[endpoint]=(row,time.monotonic(),error)
            self.stop.wait(.1)
    def read(self,name,now):
        with self.lock:row,stamp,error=self.rows.get(name,({},-1e30,'waiting'))
        return row if not error and 0<=now-stamp<=.6 else None
    def candidate(self,now):
        row=self.read('ssvep-shadow',now)
        if not row or row.get('stale') is not False:return None
        result=row.get('live')
        return result if isinstance(result,dict) and result.get('source')=='live' else None
    def mi_command(self,packet):
        allowed={'action','id','target','virtual_control','browser_onset_ms','browser_send_ms','reason'}
        if not isinstance(packet,dict) or set(packet)-allowed or packet.get('virtual_control') is True:raise ValueError('observation-only MI command required')
        request=Request(self.url+'mi-cue',data=json.dumps(packet,allow_nan=False).encode(),
                        headers={'Content-Type':'application/json','Origin':self.url.split('/api/')[0]})
        # Command thread has its own opener; the read-only poller has a separate one.
        with build_opener(ProxyHandler({})).open(request,timeout=.35) as response:data=response.read(65537)
        if len(data)>65536:raise ValueError('oversize MI reply')
        result=json.loads(data)
        if not isinstance(result,dict) or result.get('source')!='live' or result.get('control_enabled') is not False:raise ValueError('MI reply identity mismatch')
        return result
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=1.5)
