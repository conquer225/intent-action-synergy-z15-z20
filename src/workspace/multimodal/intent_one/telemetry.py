"""Read-only S3 stream. Clock values belong to the S3 boot, not the host."""
import json
import math
import socket
import threading
import time
from collections import deque

def strict_object(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError('duplicate field')
        result[key]=value
    return result

def integer(value,low=0,high=2**64-1):
    return type(value) is int and low<=value<=high

class SignalReader:
    def __init__(self):
        self.buffer=bytearray(); self.session=None; self.seq=None; self.expected=None
        self.received=None; self.last=None; self.state='waiting'; self.resets=0
    def feed(self,data,now):
        self.buffer.extend(data)
        if len(self.buffer)>8192: self.close(); raise ValueError('telemetry buffer exceeded')
        result=[]
        while b'\n' in self.buffer:
            line,_,tail=self.buffer.partition(b'\n'); self.buffer=bytearray(tail)
            if len(line)>2048: self.close(); raise ValueError('telemetry frame exceeded')
            row=json.loads(line.decode('utf-8'),object_pairs_hook=strict_object,
                           parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
            if not isinstance(row,dict) or row.get('v')!=1 or type(row.get('v')) is not int:
                raise ValueError('bad telemetry version')
            if any(not integer(row.get(k),0,2**32-1) for k in ('session','seq','dropped')) or not integer(row.get('time_us')):
                raise ValueError('bad envelope')
            kind=row.get('type')
            if kind not in ('raw','contact','signal_status'): raise ValueError('unknown telemetry type')
            if kind=='raw':
                samples=row.get('samples'); intervals=row.get('dt_us')
                if (not isinstance(samples,list) or len(samples)!=10 or any(not integer(x,0,4095) for x in samples)
                    or not isinstance(intervals,list) or len(intervals)!=10 or any(not integer(x,1,2**32-1) for x in intervals)
                    or not integer(row.get('sample_index'),0,2**32-1) or row.get('sample_rate_hz')!=500
                    or not integer(row.get('wear_mask'),0,1023) or type(row.get('valid')) is not bool):
                    raise ValueError('bad raw block')
            if kind in ('contact','signal_status') and any(type(row.get(k)) is not bool for k in ('pressed','armed')):
                raise ValueError('bad contact state')
            if kind=='contact' and (not integer(row.get('event_id'),0,2**32-1) or type(row.get('valid')) is not bool
                                    or type(row.get('strength')) not in (int,float) or not math.isfinite(row['strength'])):
                raise ValueError('bad contact event')
            changed=self.session is not None and self.session!=row['session']
            if self.session==row['session'] and self.seq is not None:
                delta=(row['seq']-self.seq)&0xffffffff
                if not 0<delta<0x80000000: continue
            if changed: self.expected=None; self.resets+=1
            discontinuity=changed
            if kind=='raw':
                discontinuity |= self.expected is not None and self.expected!=row['sample_index']
                discontinuity |= not row['valid'] or max(row['dt_us'])>6000
                self.expected=(row['sample_index']+10)&0xffffffff
                if discontinuity: self.resets+=1
            self.session=row['session']; self.seq=row['seq']; self.received=now; self.state='live'
            row=dict(row,received_at=now,discontinuity=bool(discontinuity),origin='s3_live',clock='s3_boot_us')
            self.last=row; result.append(row)
        return result
    def snapshot(self,now):
        state=self.state
        if self.received is not None and now-self.received>.5: state='stale'
        return dict(state=state,session=self.session,last=self.last if state=='live' else None,resets=self.resets)
    def close(self):
        self.state='disconnected'; self.expected=None; self.received=None; self.last=None; self.buffer.clear()

class SignalConnection:
    def __init__(self,host,port=9010):
        self.host=host; self.port=port; self.reader=SignalReader(); self.rows=deque(maxlen=64)
        self.lock=threading.Lock(); self.stop=threading.Event(); self.sock=None; self.thread=None; self.error=None
    def connect(self):
        self.sock=socket.create_connection((self.host,self.port),timeout=.5); self.sock.settimeout(.2)
        self.thread=threading.Thread(target=self._run,daemon=True); self.thread.start()
    def _run(self):
        try:
            while not self.stop.is_set():
                try: data=self.sock.recv(2048)
                except socket.timeout: continue
                if not data: break
                with self.lock:
                    for row in self.reader.feed(data,time.monotonic()):
                        if len(self.rows)==self.rows.maxlen: row['discontinuity']=True
                        self.rows.append(row)
        except (OSError,ValueError) as exc: self.error=str(exc)
        finally:
            with self.lock: self.reader.close()
    def poll(self):
        with self.lock: rows=list(self.rows); self.rows.clear(); return rows
    def close(self):
        self.stop.set()
        if self.sock:
            try: self.sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            self.sock.close()
        if self.thread: self.thread.join(timeout=1)

