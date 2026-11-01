"""Full-main virtual-time faults; recorded rejection and synthetic positive controls."""
import argparse
import contextlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import numpy as np
import cyton_guardianloop as live
from cyton_trial_recorder import TrialRecorder
from seed_shadow import SeedShadow


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True)
    p.add_argument('--output',required=True)
    args=p.parse_args()
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False)
    clock=[0.]
    live.time=SimpleNamespace(monotonic=lambda:clock[0],time=time.time,sleep=lambda _:None)
    live.configure_serial=lambda fd:None
    live.write_command=lambda fd,cmd:None
    live.configure_eeg_channels=lambda fd:None
    live.termios.tcflush=lambda fd,mode:None
    def no_pl():raise AssertionError('No PL permitted')
    live.GuardianLoopPynq=no_pl
    original_result=live.publish_result
    original_dumps=json.dumps
    def marked(payload,*a,**kw):
        if isinstance(payload,dict) and payload.get('source') in ('cyton_usb','bci'):
            payload=dict(payload,source='offline_replay_not_live',real=False,offline=True)
        return original_dumps(payload,*a,**kw)
    live.json.dumps=marked
    summaries=[]
    with np.load(args.input) as data:
        for case in ('recorded','synthetic'):
            folder=out/case;folder.mkdir()
            source=data[case]
            source_sequences=data[case+'_seq'].astype(int)
            # Synthetic length allows real algorithmic recalibration after both faults.
            source=np.tile(source,(2,1)) if case=='synthetic' else source
            counts=np.rint(source/live.DEFAULT_UV_PER_COUNT).astype(np.int64)
            results=[];events=[];faults=[];shadow=[None]
            def result(value,calibrated,path,esp32,**kwargs):
                results.append({'time':clock[0],'value':value.copy()})
                original_result(value,calibrated,path,esp32,**kwargs)
            live.publish_result=result
            def make_shadow(model,channels):
                s=SeedShadow(model,channels,source='replay',status_path=folder/'shadow.json')
                publish=s.publish
                def observed(event):
                    events.append({'time':clock[0], 'event':event.copy(),
                                   'last_gap':s.last_gap, 'mean':s.runtime.mean.tolist()})
                    publish(event)
                s.publish=observed;shadow[0]=s
                return s
            live.SeedShadow=make_shadow
            live.TrialRecorder=lambda channels,scale:TrialRecorder(channels,scale,
                control_path=folder/'no-command.json',status_path=folder/'recorder.json',record_root=folder/'records')
            live.LIVE_PATH=folder/'error.json'
            # Time gaps and counter jumps agree; recorded data also retain original sequence gap.
            schedule={22500:2.,52500:6.} if case=='synthetic' else {10000:2.}
            def packets(fd,timeout,with_timing=False,on_idle=None):
                clock[0]=0.;seq=0
                for i,row in enumerate(counts):
                    if i in schedule:
                        duration=schedule[i]
                        prior_mean=shadow[0].runtime.mean.copy()
                        clock[0]+=.6
                        on_idle(clock[0])
                        assert results[-1]['value']['valid'] is False
                        assert results[-1]['value']['emotion']['valid'] is False
                        status=json.loads(shadow[0].path.read_text())
                        assert not status['valid'] and 'class_id' not in status
                        clock[0]+=duration-.6
                        seq=(seq+round(duration*250))%256
                        faults.append({'resume_time':clock[0]+.004,'duration':duration,
                                       'mean_before':prior_mean.tolist()})
                    clock[0]+=.004
                    delta=1
                    if case=='recorded' and i:
                        delta=(int(source_sequences[i])-int(source_sequences[i-1]))%256
                    seq=(seq+delta)%256
                    frame=bytearray([0xA0,seq])
                    for v in row:frame.extend((int(v)&0xffffff).to_bytes(3,'big'))
                    frame.extend(bytes(6));frame.append(0xC0)
                    yield bytes(frame),0,clock[0]
            live.packets=packets
            clock[0]=0.
            sys.argv=['recovery-test','--port','/dev/null','--esp32-url','',
                      '--status-file',str(folder/'status.json'),'--telemetry-file',str(folder/'telemetry.json')]
            with (folder/'replay.log').open('w') as log,contextlib.redirect_stdout(log):
                live.main()
            assert results[-1]['value']['reason']=='SERVICE_STOPPED_OR_STREAM_TIMEOUT'
            assert not results[-1]['value']['valid']
            checks=[]
            for f in faults:
                t=f['resume_time']
                gap_events=[e for e in events if abs(e['time']-t)<.001 and e['last_gap']]
                assert gap_events
                e=gap_events[0]
                retained=e['last_gap']['baseline_retained']
                expected=case=='synthetic' and f['duration']==2.
                assert retained==expected,(case,f,e)
                if retained:np.testing.assert_array_equal(e['mean'],f['mean_before'])
                after=[r for r in results if r['time']>=t and 'packets_seen' in r['value']]
                windows=[r for r in after if r['value'].get('sqi') is not None]
                assert windows and windows[0]['time']-t>=7.99
                assert not windows[0]['value']['emotion']['valid']
                assert windows[0]['value']['calibration_current']<=1
                prediction=next((e for e in events if e['time']>t and e['event']['state']=='prediction'),None)
                if case=='synthetic':
                    assert prediction is not None
                    assert prediction['time']-t >= (13.99 if retained else 73.99)
                checks.append({'gap_seconds':f['duration'],'seed_baseline_retained':retained,
                               'first_primary_window_after_s':windows[0]['time']-t,
                               'first_seed_prediction_after_s':None if prediction is None else prediction['time']-t,
                               'old_results_invalidated':True,'primary_calibration_restarted':True})
            (folder/'events.json').write_text(json.dumps({'faults':faults,'seed_events':events,'checks':checks},indent=2))
            summaries.append({'case':case,'checks':checks,'passed':True})
    (out/'report.json').write_text(json.dumps({'cases':summaries,'scope':'Virtual-time packet main-loop faults; not physical USB fault or labeled emotion test.'},indent=2))
    print(json.dumps(summaries,indent=2))


if __name__=='__main__':main()
