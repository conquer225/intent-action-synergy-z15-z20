"""One selected controller, explicit enabling, no command retry or replay."""
from collections import deque

class TaskController:
    def __init__(self,factory):
        self.factory=factory; self.peer=None; self.mode=None; self.device=None
        self.enabled=False; self.generation=0; self.seen=deque(maxlen=128); self.timeline=deque(maxlen=128)
    def _send(self,device,action,**fields):
        reply=self.peer.send(device,action,**fields)
        self.timeline.append(dict(device=device,action=action,accepted=reply.get('ok') is True))
        if reply.get('ok') is not True: raise RuntimeError(reply.get('error','rejected'))
        return reply
    def select(self,mode,device):
        if mode not in ('eye','brain','contact','mpu') or device not in ('hand','pendulum'):
            raise ValueError('unknown task')
        if (mode=='contact' and device!='hand') or (mode=='mpu' and device!='pendulum'):
            raise ValueError('local input requires its matching device')
        self.estop(); self.generation+=1
        if self.peer: self.peer.close(); self.peer=None
        source=mode if mode in ('eye','brain') else 'pc'
        peer=self.factory(source); peer.connect(); self.peer=peer
        try:
            self._send('all','estop')
            status=self._send('all','status').get('status',{})
            if any(status.get(d,{}).get('enabled') is not False for d in ('hand','pendulum')):
                raise RuntimeError('stopped status not confirmed')
            if mode=='contact': self._send('hand','input',input='contact')
            else: self._send(device,'mode',mode='tilt_test' if mode=='mpu' else 'network')
            self.mode,self.device=mode,device
        except Exception:
            self.close(); raise
    def enable(self):
        if not self.peer: raise RuntimeError('select a task first')
        self._send(self.device,'enable'); self.enabled=True
    def zero(self):
        if self.mode!='mpu' or self.enabled: raise RuntimeError('select stopped MPU task first')
        self._send('pendulum','zero')
    def sync(self,status):
        if self.enabled and status.get(self.device,{}).get('enabled') is not True:
            self.estop()
    def action(self,action):
        if not self.enabled or self.mode not in ('eye','brain'): raise RuntimeError('selected network task must be enabled')
        allowed=('open','close') if self.device=='hand' else ('start','stop','left','right')
        if action not in allowed: raise ValueError('wrong device action')
        if action=='stop': self.estop(); return
        self._send(self.device,action)
    def event(self,row,now):
        token=(row.get('session'),row.get('id'))
        if (not self.enabled or row.get('mode')!=self.mode or row.get('valid') is not True
            or row.get('generation',self.generation)!=self.generation or token in self.seen
            or type(row.get('received_at')) not in (int,float) or not 0<=now-row['received_at']<=.3
            or type(row.get('age_s')) not in (int,float) or not 0<=row['age_s']<=.3): return False
        self.seen.append(token); self.action(row['action']); return True
    def estop(self):
        self.enabled=False
        if self.peer and self.peer.connected: self._send('all','estop')
    def close(self):
        try: self.estop()
        finally:
            if self.peer: self.peer.close(); self.peer=None
            self.enabled=False; self.mode=self.device=None

