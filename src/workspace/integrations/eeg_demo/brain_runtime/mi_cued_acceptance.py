"""Bounded, recorded-only MI acceptance; no serial, PL or actuator access."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

import numpy as np
import scipy

from mi_cued import CuedMISession
from mi_cued_replay import load_recording
from mi_eegnet_portable import OfflineEEGNet


class Clock:
    def __init__(self):
        self.value = 100.

    def __call__(self):
        return self.value


class TimedModel:
    def __init__(self, model):
        self.model = model
        self.times = []

    def logits(self, values):
        before = time.perf_counter()
        result = self.model.logits(values)
        self.times.append((time.perf_counter()-before)*1000)
        return result


def timings(values):
    return dict(count=len(values),median_ms=float(np.median(values)),
                p95_ms=float(np.quantile(values,.95)),p99_ms=float(np.quantile(values,.99)),
                max_ms=float(np.max(values)))


def cue_counts(samples):
    starts = list(range(750,samples,2000))
    rest = sum(i%3==2 for i in range(len(starts)))
    incomplete = sum(i%3!=2 and start+625>samples for i,start in enumerate(starts))
    return dict(trials=len(starts),rest=rest,complete=len(starts)-rest-incomplete,
                incomplete=incomplete)


def dump(path, data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def logical_replay(model, raw, sequences, out, paced=False, *, virtual_control=False):
    clock = time.monotonic if paced else Clock()
    measured = TimedModel(model)
    session = CuedMISession(measured,source='replay',clock=clock,log_path=out/'events.jsonl')
    durations, lateness, trace, results = [], [], [], []
    conditioned, filtered = np.empty_like(raw,dtype=float), np.empty_like(raw,dtype=float)
    valid = np.zeros(len(raw),dtype=bool)
    begun, cpu = time.monotonic(), time.process_time()
    trials = 0
    for start in range(0,len(raw),50):
        end = min(start+50,len(raw))
        if start % 2000 == 750:
            if session.trial and session.trial['state'] in ('active','awaiting_presentation'):
                session.command(dict(action='stop',id=session.trial['id']))
            target = ('left','right','rest')[trials%3]
            state = session.command(dict(action='start',target=target,virtual_control=virtual_control))
            session.command(dict(action='presented',id=state['id'],browser_onset_ms=1,browser_send_ms=2))
            trials += 1
        if paced:
            deadline = begun+end/250
            remaining = deadline-time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            now = time.monotonic()
            received = min(deadline,now)
            lateness.append(max(0,now-deadline)*1000)
        else:
            clock.value += (end-start)/250
            received = clock.value
        before = time.perf_counter()
        state = session.feed(raw[start:end],sequences[start:end],received_monotonic=received)
        durations.append((time.perf_counter()-before)*1000)
        # A reset has too few samples; retain NaNs as evidence instead of fabricating parity.
        width = end-start
        conditioned[start:end] = session.raw[-width:] if len(session.raw)>=width else np.nan
        filtered[start:end] = session.filtered[-width:] if len(session.filtered)>=width else np.nan
        valid[start:end] = len(session.filtered)>=width
        trace.append(dict(sample_end=end,state=state['state'],reason=state['reason'],
                          input_state=state['input_state'],target=state['target'],
                          source=state['source'],control_enabled=state['control_enabled']))
        if state['result'] and not any(row['trial']==trials for row in results):
            results.append(dict(trial=trials,target=state['target'],**state['result']))
        if state['state']=='active':
            session.command(dict(action='heartbeat',id=state['id']))
        if start % 2000 == 1750 and session.trial:
            session.command(dict(action='stop',id=session.trial['id']))
        if start % 2500 == 0:
            print('MI_REPLAY_PROGRESS',end,'/',len(raw),'paced',paced,flush=True)
    incomplete_withdrawn = bool(session.trial and session.trial['target']!='rest'
        and session.trial['state']=='active' and session.trial['result'] is None)
    session.disconnect('replay_eof')
    final = session.snapshot()
    wall = time.monotonic()-begun
    summary = dict(samples=len(raw),trials=trials,candidates=len(results),source='replay',
                   rest_trials=cue_counts(len(raw))['rest'],
                   incomplete_trial_withdrawn=incomplete_withdrawn,
                   valid_samples=int(np.sum(valid)),invalid_samples=int(np.sum(~valid)),
                   batch=timings(durations),inference=timings(measured.times),
                   wall_seconds=wall,cpu_seconds=time.process_time()-cpu,
                   eof_withdrawn=final['result'] is None and final['input_state']=='no_data',
                   rejection_batches=sum(row['state']=='rejected' for row in trace),
                   virtual_commands=session.virtual_hand['command_count'],
                   virtual_stopped=not final['virtual_hand']['enabled'],
                   labels_read=False,accuracy_scored=False,control_enabled=False)
    if paced:
        late = np.asarray(lateness)
        summary.update(schedule_lateness_ms=timings(late),
                       last_decile_median_lateness_ms=float(np.median(late[-78:])),
                       first_decile_median_lateness_ms=float(np.median(late[:78])))
        summary['paced_gate_passed'] = bool(summary['batch']['p99_ms']<200
            and late.max()<500 and summary['candidates']==13 and summary['rest_trials']==6
            and summary['rejection_batches']==0 and summary['eof_withdrawn']
            and incomplete_withdrawn and np.array_equal(np.flatnonzero(~valid),np.arange(50)))
    dump(out/'replay.json',dict(summary=summary,trace=trace,results=results))
    np.savez_compressed(out/'arrays.npz',conditioned=conditioned,filtered=filtered,
                        valid=valid,logits=np.array([row['logits'] for row in results]))
    return summary


def recovery(model):
    clock = Clock()
    session = CuedMISession(model,source='replay',clock=clock)
    counter = 0
    def feed(count):
        nonlocal counter
        for start in range(0,count,50):
            width = min(50,count-start)
            samples = np.arange(counter,counter+width)
            raw = 10*np.sin(2*np.pi*samples[:,None]/250*np.arange(8,16)[None])
            clock.value += width/250
            session.feed(raw,samples%256)
            counter += width
            if session.trial and session.trial['state']=='active':
                session.command(dict(action='heartbeat',id=session.trial['id']))
    def start():
        state = session.command(dict(action='start',target='left'))
        return session.command(dict(action='presented',id=state['id'],browser_onset_ms=1,browser_send_ms=2))
    feed(750)
    start()
    feed(650)
    before = session.snapshot()
    assert before['result'] is not None
    gap = session.feed(np.ones((1,8)),np.array([(counter+1)%256]))
    assert gap['result'] is None and gap['reason']=='sequence_gap_or_stall'
    assert gap['received_samples']==0
    warm = start()
    assert warm['result'] is None and warm['reason']=='filter_warmup_required'
    feed(750)
    start()
    feed(650)
    recovered = session.snapshot()
    assert recovered['result'] is not None
    clock.value += .51
    stale = session.snapshot()
    assert stale['result'] is None and stale['reason']=='no_fresh_data'
    session.disconnect('transport_disconnected')
    final = session.snapshot()
    assert final['result'] is None and final['received_samples']==0
    return dict(candidate_before=True,gap_withdrawn=True,reset_samples=0,
                premature_reuse_refused=True,rewarm_and_new_window_recovered=True,
                stale_withdrawn=True,disconnect_withdrawn=True,control_enabled=False)


def request(port, body=None):
    base = 'http://127.0.0.1:'+str(port)
    req = Request(base+'/api/mi-cue',data=json.dumps(body).encode() if body else None,
                  headers={'Content-Type':'application/json','Origin':base})
    with urlopen(req,timeout=1) as response:
        return json.load(response)


def wait_ready(process, port, warm=False):
    deadline = time.monotonic()+15
    while time.monotonic()<deadline:
        if process.poll() is not None:
            raise RuntimeError('Isolated HTTP child exited')
        try:
            state = request(port)
            if not warm or state['input_state']=='ready':
                return state
        except (URLError,ConnectionError,TimeoutError):
            pass
        time.sleep(.1)
    raise TimeoutError('Isolated HTTP child not ready')


def end_child(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def http_recovery(model_path, input_path, out):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port = sock.getsockname()[1]
    app = Path(__file__).resolve().parent
    process = None
    with (out/'http_child.log').open('w') as log:
        try:
            process = subprocess.Popen([sys.executable,str(app/'mi_cued_replay.py'),
                '--model',str(model_path),'--input',str(input_path),'--allow-experimental',
                '--port',str(port)],stdout=log,stderr=log)
            wait_ready(process,port,warm=True)
            state = request(port,dict(action='start',target='left'))
            trial_id = state['id']
            request(port,dict(action='presented',id=trial_id,browser_onset_ms=1,browser_send_ms=2))
            deadline = time.monotonic()+7
            candidate = None
            while time.monotonic()<deadline:
                state = request(port,dict(action='heartbeat',id=trial_id))
                if state['result'] is not None:
                    candidate = state['result']
                    break
                time.sleep(.1)
            assert candidate is not None and candidate['source']=='replay'
            end_child(process)
            try:
                request(port)
            except (URLError,ConnectionError,TimeoutError):
                endpoint_closed = True
            else:
                raise AssertionError('Terminated child still served results')
            process = subprocess.Popen([sys.executable,str(app/'mi_cued_server.py'),
                '--source','replay','--port',str(port)],stdout=log,stderr=log)
            restarted = wait_ready(process,port)
            assert restarted['id'] is None and restarted['result'] is None
            assert restarted['input_state']=='no_data'
            return dict(candidate_before_exit=True,endpoint_closed=endpoint_closed,
                        restart_no_old_id=True,restart_no_result=True,restart_no_data=True,
                        bind='127.0.0.1',port=port,control_enabled=False)
        finally:
            if process is not None:
                end_child(process)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--probes',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--allow-experimental',action='store_true')
    parser.add_argument('--paced',action='store_true')
    parser.add_argument('--http-recovery',action='store_true')
    args = parser.parse_args()
    if not args.allow_experimental:
        parser.error('Explicit experimental opt-in required')
    args.output.mkdir(exist_ok=False)
    model = OfflineEEGNet(args.model,allow_experimental=True)
    with np.load(args.probes,allow_pickle=False) as data:
        waves, indices = data['waveforms'],data['indices']
    if waves.shape != (256,8,500) or not np.isfinite(waves).all():
        raise ValueError('Fixed 256 finite probe windows required')
    all_logits = []
    for start in range(0,len(waves),8):
        all_logits.append(model.logits(waves[start:start+8]))
        if start % 32 == 0:
            print('MI_NUMERICAL_PROGRESS',start+8,'/',len(waves),flush=True)
    np.savez_compressed(args.output/'probes.npz',indices=indices,logits=np.concatenate(all_logits))
    raw, sequences = load_recording(args.input)
    summary = logical_replay(model,raw,sequences,args.output,paced=args.paced)
    faults = recovery(model)
    http = http_recovery(args.model,args.input,args.output) if args.http_recovery else None
    rss = None
    if sys.platform.startswith('linux'):
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report = dict(summary=summary,fault_checks=faults,http_recovery=http,
                  python=sys.version,numpy=np.__version__,scipy=scipy.__version__,
                  max_rss_kib=rss,platform=sys.platform,
                  scope='isolated recorded MI only; not production full-stack or accuracy',
                  promotion_gate_passed=False,production_eligible=False,control_enabled=False)
    dump(args.output/'report.json',report)
    print('MI_ACCEPTANCE_FINISHED',json.dumps(summary),flush=True)


if __name__=='__main__':
    main()
