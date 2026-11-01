"""Bounded automatic HTTP cues for recorded-only five-task acceptance."""
import json
from pathlib import Path
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import mi_acquisition
import replay_release_audit

performance_only=False


class ObservedRuntime(mi_acquisition.MICandidateRuntime):
    def __init__(self,*args,**kwargs):
        if not performance_only:kwargs['audit_directory']=Path(kwargs['log_path']).parent
        super().__init__(*args,**kwargs)
        self.started=time.monotonic()
        self.observations=[]
        self.http_errors=[]
        self.candidates={}
        self.cues=[]
        self.expected_command_races=[]
        self.stop_driver=threading.Event()
        self.driver=threading.Thread(target=self._drive,name='mi-replay-http-cues',daemon=True)
        self.driver.start()
        instances.append(self)

    def request(self,path,body=None):
        url='http://127.0.0.1:'+str(self.server.server_port)
        request=Request(url+path,data=None if body is None else json.dumps(body).encode(),
                        headers={'Content-Type':'application/json','Origin':url})
        with urlopen(request,timeout=3) as response:
            return json.load(response)

    def _drive(self):
        trial=None
        cue_number=-1
        dashboard = {}
        dashboard_at = -float('inf')
        try:
            with urlopen('http://127.0.0.1:'+str(self.server.server_port)+'/') as response:
                if b'/api/mi-cue' not in response.read():
                    raise ValueError('Missing candidate entry')
            while not self.stop_driver.wait(.4):
                elapsed=time.monotonic()-self.started
                state=self.request('/api/mi-cue',None if trial is None else
                                   dict(action='heartbeat',id=trial))
                if elapsed-dashboard_at >= 1:
                    dashboard=self.request('/api/multitask')
                    dashboard_at=elapsed
                self.observations.append(dict(dashboard, elapsed_seconds=elapsed, mi=state,
                                               dashboard_observed_seconds=dashboard_at))
                number=int((elapsed-3)//8)
                target=('left','right','rest','left')[number%4]
                if elapsed>=3 and number!=cue_number and (target=='rest' or
                        (state['input_state']=='ready' and state.get('quality',{}).get('ready',True))):
                    if trial is not None:
                        self.request('/api/mi-cue',dict(action='stop',id=trial))
                    state=self.request('/api/mi-cue',dict(action='start',target=target))
                    trial=state['id']; cue_number=number
                    try:
                        self.request('/api/mi-cue',dict(action='presented',id=trial,
                                                      browser_onset_ms=1,browser_send_ms=2))
                    except HTTPError as exc:
                        current=self.request('/api/mi-cue')
                        if exc.code!=400 or current['id']!=trial or current['state']!='rejected':
                            raise
                        self.expected_command_races.append(dict(id=trial,elapsed_seconds=elapsed,
                                                                reason=current['reason']))
                    self.cues.append(dict(elapsed_seconds=elapsed,target=target,id=trial,
                                          scripted_replay_not_browser_optical=True))
                if state['result'] is not None and state['id'] not in self.candidates:
                    self.candidates[state['id']]=dict(elapsed_seconds=elapsed,target=state['target'],
                        id=state['id'],**state['result'])
        except (URLError,OSError,ValueError,KeyError) as exc:
            self.http_errors.append(f'{type(exc).__name__}: {exc}')

    def close(self):
        self.stop_driver.set(); self.driver.join(timeout=4)
        super().close()
        self.final=self.session.snapshot()


instances=[]


def main():
    global performance_only
    if '--performance-only' in sys.argv:
        sys.argv.remove('--performance-only');performance_only=True
    out=Path(sys.argv[sys.argv.index('--output')+1]).resolve()
    mi_acquisition.MICandidateRuntime=ObservedRuntime
    try:
        if performance_only:
            import soak_service_replay
            soak_service_replay.main()
        else:replay_release_audit.main()
    finally:
        if out.is_dir():
            result=[]
            for runtime in instances:
                result.append(dict(cues=runtime.cues,candidates=list(runtime.candidates.values()),
                    worker_backend='isolated_ARM_process',
                    http_errors=runtime.http_errors,adapter_stats=(runtime.adapter.stats
                        if runtime.adapter is not None else {'reader_packets_offered':runtime.reader_sink.offered}),
                    expected_command_races=runtime.expected_command_races,
                    adapter_error=runtime.adapter.error if runtime.adapter is not None else runtime.session.error,
                    final=runtime.session.snapshot(),
                    threads_stopped=not any(t.is_alive() for t in
                        ((runtime.driver,runtime.thread,runtime.adapter.worker) if runtime.adapter is not None
                         else (runtime.driver,runtime.thread))),
                    port=runtime.server.server_port,observations=runtime.observations))
            (out/'mi-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
