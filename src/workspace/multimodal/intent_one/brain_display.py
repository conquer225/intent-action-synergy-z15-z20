"""Brain results are references only; this module has no actuator transport."""
import threading,queue,time
CHANNELS=['F3','F4','C3','C4','T7','T8','O1','O2']

class BrainDisplay:
    def observe(self,status,mi):
        fatigue=status.get('fatigue',{}) if isinstance(status,dict) and status.get('stale') is False else {}
        live=fatigue.get('offline') is not True
        emotion=fatigue.get('emotion',{}) if live else {}
        row=mi if isinstance(mi,dict) else {}
        ready=(row.get('source')=='live' and row.get('enabled') is True and row.get('input_state')=='ready'
               and row.get('quality',{}).get('ready') is True and row.get('control_enabled') is False
               and row.get('production_eligible') is False and row.get('channels')==CHANNELS
               and row.get('state')=='active' and row.get('model_status')=='experimental_unpromoted')
        result=row.get('result') if ready else None
        if not isinstance(result,dict) or result.get('source')!='live' or result.get('control_enabled') is not False or result.get('label') not in ('left','right'):
            result=None
        return dict(fatigue=fatigue.get('level') if live and fatigue.get('valid') is True else None,
                    emotion=emotion.get('label') if emotion.get('valid') is True else None,
                    mi_label=result.get('label') if result else None,mi_state=row.get('state','waiting'),
                    mi_target=row.get('target'),mi_reason=row.get('reason'),mi_enabled=row.get('enabled') is True,
                    mi_trial_id=row.get('id'),mi_scope='experimental_observation_only')

class MiTrial:
    def __init__(self,send):self.send=send;self.id=None;self.waiting=False;self.last_heartbeat=0
    def start(self,target,now):
        if target not in ('left','right','rest'):raise ValueError('MI target must be left/right/rest')
        self.stop();row=self.send(dict(action='start',target=target,virtual_control=False))
        if not isinstance(row,dict) or row.get('state')!='awaiting_presentation' or not isinstance(row.get('id'),str):raise RuntimeError('MI trial start rejected')
        self.id=row['id'];self.waiting=True;self.last_heartbeat=now
    def presented(self,now):
        if not self.waiting:return
        row=self.send(dict(action='presented',id=self.id,browser_onset_ms=now*1000,browser_send_ms=now*1000))
        if row.get('state')!='active':self.id=None;self.waiting=False;raise RuntimeError('MI presentation rejected')
        self.waiting=False;self.last_heartbeat=now
    def tick(self,now):
        if self.id and not self.waiting and now-self.last_heartbeat>=.4:
            row=self.send(dict(action='heartbeat',id=self.id));self.last_heartbeat=now
            if row.get('state')!='active':self.id=None
    def stop(self):
        ident=self.id;self.id=None;self.waiting=False
        if ident:self.send(dict(action='stop',id=ident,reason='page_hidden'))

class MiWorker:
    """Bounded trial-command worker keeps HTTP waits outside HDMI and button polling."""
    def __init__(self,send):
        self.trial=MiTrial(send);self.jobs=queue.Queue(maxsize=8);self.done=threading.Event();self.lock=threading.Lock()
        self.waiting=False;self.error=None;self.target=None;self.present_pending=False
        self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()
    def start(self,target):self.jobs.put_nowait(('start',target,time.monotonic()))
    def presented(self,now):
        with self.lock:
            if not self.waiting or self.present_pending:return
            self.present_pending=True
        self.jobs.put_nowait(('presented',None,now))
    def stop(self):
        while True:
            try:self.jobs.get_nowait()
            except queue.Empty:break
        with self.lock:self.target=None;self.waiting=False
        self.jobs.put_nowait(('stop',None,time.monotonic()))
    def snapshot(self):
        with self.lock:return dict(waiting=self.waiting,target=self.target,error=self.error)
    def _run(self):
        try:
            while not self.done.is_set():
                try:action,value,now=self.jobs.get(timeout=.05)
                except queue.Empty:action=None
                try:
                    if action=='start':self.trial.start(value,now);self.target=value
                    elif action=='presented':self.trial.presented(now)
                    elif action=='stop':self.trial.stop();self.target=None
                    self.trial.tick(time.monotonic())
                    with self.lock:self.waiting=self.trial.waiting;self.present_pending=False;self.error=None
                except (OSError,ValueError,RuntimeError) as exc:
                    self.trial.id=None;self.trial.waiting=False
                    with self.lock:self.waiting=False;self.present_pending=False;self.error=str(exc)
        finally:
            try:self.trial.stop()
            except (OSError,ValueError,RuntimeError):pass
    def close(self):
        self.done.set();self.thread.join(timeout=1.5)
        if self.thread.is_alive():raise RuntimeError('MI command worker did not stop')
