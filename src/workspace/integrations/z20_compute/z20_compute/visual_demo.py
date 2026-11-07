"""Four-mode display state; no acquisition, renderer or actuator ownership."""
from collections import OrderedDict,deque
import threading
import time
import uuid
import math

MODES = ('fluid', 'spectrum', 'npu', 'spatial')


class DemoState:
    def __init__(self, *, now=time.monotonic, ttl=2.0):
        self.now, self.ttl = now, ttl
        self.lock = threading.RLock()
        self.session = uuid.uuid4().hex
        self.epoch, self.mode_index, self.sample_index = 0, 0, 0
        self.menu, self.stopped = True, False
        self.clients = OrderedDict()
        self.action_id, self.action = 0, None
        self.actions=deque(maxlen=32)
        self.frame, self.sequence, self.received = None, -1, -float('inf')
        self.heartbeat = -float('inf')
        self.accepted_frames, self.rejected_frames = 0, 0
        self.data = {}
        self.sound_input=None
        self.sound_sample_index=0
        self.map_backend='original'
        self.geometry=None;self.geometry_sequence=-1;self.geometry_received=-float('inf')
        self.map_view=0;self.map_available=False

    def accept_sound(self,row):
        """One explicitly captured sound window; never activates an actuator."""
        vector=row.get('vector');valid=row.get('valid',True)
        if (type(valid) is not bool or (valid and (not isinstance(vector,list) or len(vector)!=40
                or any(type(v) not in (float,int) or not math.isfinite(v) or abs(v)>1e6 for v in vector)))
                or (not valid and vector is not None)
                or row.get('source') not in ('live:pc_microphone','recorded:pc_wav')
                or not isinstance(row.get('window_id'),str) or not 1<=len(row['window_id'])<=96):
            raise ValueError('invalid sound feature window')
        with self.lock:
            if (row.get('session')!=self.session or row.get('epoch')!=self.epoch
                    or self.menu or MODES[self.mode_index]!='npu'
                    or (self.sound_input or {}).get('window_id')==row['window_id']):
                return dict(self.snapshot(),accepted=False)
            self.sample_index=2;self._invalidate()
            self.sound_input=dict(vector=vector,valid=valid,source=row['source'],window_id=row['window_id'],
                                  reason='ok' if valid else 'silence_or_insufficient_signal')
            return dict(self.snapshot(),accepted=True)

    def _invalidate(self):
        self.epoch += 1
        self.frame, self.sequence, self.received = None, -1, -float('inf')
        self.data = {}
        self.action=None;self.actions.clear()
        self.geometry=None;self.geometry_sequence=-1;self.geometry_received=-float('inf')

    def attach_renderer(self):
        with self.lock:
            self.sound_input=None
            self.session = uuid.uuid4().hex
            self._invalidate()
            self.heartbeat = self.now()
            return self.session

    def touch(self, session):
        with self.lock:
            if session != self.session:return False
            self.heartbeat = self.now()
            return True

    def detach_renderer(self, session):
        with self.lock:
            if session == self.session:
                self.sound_input=None
                self.heartbeat = -float('inf')
                self._invalidate()

    def command(self, client, sequence, name):
        if (not isinstance(client,str) or not 1 <= len(client) <= 64
                or type(sequence) is not int or sequence < 0
                or name not in ('left','right','enter','back','stop','recorded_sound_0','recorded_sound_1','recorded_sound_2','map_pl','map_original')):
            raise ValueError('invalid display command')
        with self.lock:
            if sequence <= self.clients.get(client,-1):
                return dict(self.snapshot(),accepted=False)
            self.clients[client]=sequence;self.clients.move_to_end(client)
            while len(self.clients)>64:self.clients.popitem(last=False)
            self.stopped=False
            mode=MODES[self.mode_index]
            if name in ('map_pl','map_original'):
                if self.menu or mode!='spatial' or (name=='map_pl' and not self.map_available):
                    return dict(self.snapshot(),accepted=False)
                self.map_backend='pl' if name=='map_pl' else 'original';self._invalidate()
            elif name.startswith('recorded_sound_'):
                if self.menu or mode!='npu':return dict(self.snapshot(),accepted=False)
                self.sample_index=2;self.sound_sample_index=int(name[-1]);self.sound_input=None;self._invalidate()
            elif name in ('back','stop'):
                self.menu=True;self.stopped=name=='stop';self._invalidate()
            elif self.menu:
                if name=='enter':self.menu=False
                else:self.mode_index=(self.mode_index+(-1 if name=='left' else 1))%len(MODES)
                self._invalidate()
            elif name=='enter':
                # Only the mode selector uses enter. Never infer a physical action.
                return dict(self.snapshot(),accepted=True)
            elif mode=='fluid':
                self.action_id+=1
                self.action=dict(id=self.action_id,name='inject_'+name,epoch=self.epoch)
                self.actions.append((self.now(),dict(self.action)))
            elif mode in ('spectrum','npu'):
                self.sample_index=(self.sample_index+(-1 if name=='left' else 1))%3
                self._invalidate()
            else:
                if name=='left':self._invalidate()
                else:self.map_view=(self.map_view+1)%3
                self.action_id+=1
                self.action=dict(id=self.action_id,name='capture' if name=='left' else 'view_next',epoch=self.epoch)
                self.actions.append((self.now(),dict(self.action)))
            return dict(self.snapshot(),accepted=True)

    def accept_frame(self, session, epoch, sequence, jpeg):
        if not isinstance(jpeg,bytes) or not 1<=len(jpeg)<=1024*1024:
            raise ValueError('frame payload out of bounds')
        with self.lock:
            if (session!=self.session or type(epoch) is not int or epoch!=self.epoch
                    or type(sequence) is not int or sequence<=self.sequence
                    or (MODES[self.mode_index]=='spatial' and self.map_backend=='pl' and not self.menu)):
                self.rejected_frames+=1;return False
            self.frame,self.sequence,self.received=jpeg,sequence,self.now()
            self.heartbeat=self.received;self.accepted_frames+=1
            return True

    def latest(self):
        with self.lock:
            if not 0<=self.now()-self.received<=self.ttl:return None
            return self.epoch,self.sequence,self.frame

    def accept_geometry(self,session,epoch,sequence,geometry):
        from .visual_wire import GeometryFrame
        if not isinstance(geometry,GeometryFrame):raise ValueError('expected validated geometry')
        with self.lock:
            if (session!=self.session or type(epoch) is not int or epoch!=self.epoch
                    or type(sequence) is not int or sequence<=self.geometry_sequence
                    or self.menu or MODES[self.mode_index]!='spatial' or self.map_backend!='pl'):
                self.rejected_frames+=1;return False
            self.geometry,self.geometry_sequence,self.geometry_received=geometry,sequence,self.now()
            self.heartbeat=self.geometry_received;self.accepted_frames+=1;return True

    def latest_geometry(self):
        with self.lock:
            if (self.menu or MODES[self.mode_index]!='spatial' or self.map_backend!='pl'
                    or self.geometry is None or not 0<=self.now()-self.geometry_received<=self.ttl):return None
            return self.session,self.epoch,self.geometry_sequence,self.geometry

    def publish(self, key, payload, *, epoch):
        with self.lock:
            if epoch!=self.epoch:return False
            self.data[key]=(self.now(),payload)
            return True

    def snapshot(self):
        with self.lock:
            now=self.now()
            online=0<=now-self.heartbeat<=self.ttl
            return dict(session=self.session,epoch=self.epoch,mode=MODES[self.mode_index],
                menu=self.menu,stopped=self.stopped,sample_index=self.sample_index,
                sound_input=dict(self.sound_input) if self.sound_input else None,
                sound_sample_index=self.sound_sample_index,
                map_backend=self.map_backend,geometry_sequence=self.geometry_sequence,
                map_view=self.map_view,map_available=self.map_available,
                action=dict(self.action) if self.action else None,
                actions=[dict(action) for at,action in self.actions if 0<=now-at<=self.ttl],
                renderer_online=online,
                frame_valid=0<=now-self.received<=self.ttl,
                frame_sequence=self.sequence,accepted_frames=self.accepted_frames,
                rejected_frames=self.rejected_frames,actuator_control=False,
                data={k:v for k,(at,v) in self.data.items() if online and 0<=now-at<=self.ttl})
