"""One cached read-only loopback observation, shared by all demo viewers."""
import copy
import json
import math
import threading
import time
import urllib.request

CAP=['F3','F4','C3','C4','T7','T8','O1','O2']
PATHS=('/api/status','/api/telemetry')


class DemoBridge:
    def __init__(self,fetch=None,clock=time.monotonic,autostart=True):
        self.fetch=fetch or self._fetch;self.clock=clock
        self.lock=threading.Lock();self.stop=threading.Event()
        self.row={};self.updated=-math.inf;self.error='等待脑电采集服务'
        self.worker=None
        if autostart:
            self.worker=threading.Thread(target=self._run,name='eeg-demo-readonly',daemon=True)
            self.worker.start()

    def _fetch(self,path):
        if path not in PATHS:raise ValueError('Unknown read-only endpoint')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:9102'+path,timeout=.7) as response:
            raw=response.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('Upstream response too large')
        return json.loads(raw,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))

    def refresh(self):
        try:
            status=self.fetch(PATHS[0]);telemetry=self.fetch(PATHS[1])
            if not isinstance(status,dict) or not isinstance(telemetry,dict):raise ValueError('Invalid upstream')
            fatigue=status.get('fatigue') or {};wave=telemetry.get('telemetry') or {}
            if (status.get('stale') is not False or telemetry.get('stale') is not False
                or fatigue.get('offline') or fatigue.get('source') not in ('bci','cyton_usb')
                or fatigue.get('channel_map')!=CAP or wave.get('channels')!=CAP
                or wave.get('real') is not True or wave.get('offline')):
                raise ValueError('等待新鲜的固定八通道脑电')
            samples,raw=wave.get('samples'),wave.get('raw_samples')
            if (not isinstance(samples,list) or not 1<=len(samples)<=1500
                or not isinstance(raw,list) or len(raw)!=len(samples)
                or any(not isinstance(row,list) or len(row)!=8
                       or any(type(x) not in (int,float) or not math.isfinite(x) for x in row)
                       for row in samples+raw)):
                raise ValueError('Invalid waveform shape')
            row=dict(status={key:status[key] for key in ('fatigue','system','server_time') if key in status},
                     telemetry=wave,data_age_seconds=telemetry.get('data_age_seconds'),
                     received_at=time.time())
            with self.lock:self.row=row;self.updated=self.clock();self.error=None
        except (OSError,ValueError,TypeError,KeyError,TimeoutError) as error:
            with self.lock:self.row={};self.updated=-math.inf;self.error=str(error)

    def snapshot(self):
        with self.lock:
            age=self.clock()-self.updated
            upstream=self.row.get('data_age_seconds')
            stale=not 0<=age<=3 or (type(upstream) in (int,float) and upstream+age>3)
            view=copy.deepcopy(self.row) if not stale else dict(status={},telemetry={})
            return dict(view,format='guardianloop-eeg-live-v1',origin='live',stale=stale,
                        bridge_age_seconds=age if math.isfinite(age) else None,
                        reason=self.error or ('数据已过期' if stale else ''),control_enabled=False)

    def _run(self):
        while not self.stop.is_set():
            start=self.clock();self.refresh()
            self.stop.wait(max(.05,1-(self.clock()-start)))

    def close(self):
        self.stop.set()
        if self.worker:self.worker.join(2)
