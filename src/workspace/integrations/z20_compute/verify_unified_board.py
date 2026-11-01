"""Actual wired PL, nine views, silent local audio and camera integration evidence."""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import socket
import threading
import time
import urllib.request
import numpy as np
from z20_compute.service import FeaturePublisher
from z20_compute.training import Dataset,ModelBundle,PREPROCESSORS
from z20_compute.headless_keys import Navigation


class AuditPublisher(FeaturePublisher):
    """Keep bounded window evidence before the normal latest-result cache replaces it."""
    def __init__(self,sock):
        super().__init__(sock);self.audit_lock=threading.Lock();self.received={}

    def _receive(self,message):
        if message.kind=='result' and 'window_id' in message.body:
            with self.audit_lock:
                key=(message.body['task'],message.body['window_id']);self.received[key]=message.body
                while len(self.received)>128:self.received.pop(next(iter(self.received)))
        super()._receive(message)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True)
    parser.add_argument('--seconds',type=float,default=1800)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--assets-root',type=Path,default=Path('artifacts/headless'))
    parser.add_argument('--models-root',type=Path)
    args=parser.parse_args()
    report=dict(passed=False,running=True,scope='actual wired unified service; physical onsite gates excluded',
        errors=[],sound_windows=0,eeg_windows=0,reconnects=0,pages=[],samples=[],latest_input_retries=[])
    started=time.monotonic();client=None
    def save():
        report['elapsed_seconds']=time.monotonic()-started
        args.output.parent.mkdir(parents=True,exist_ok=True)
        temp=args.output.with_suffix('.tmp');temp.write_text(json.dumps(report,indent=2),encoding='utf-8');temp.replace(args.output)
    def get(path):return urllib.request.urlopen('http://'+args.host+':9021/'+path,timeout=6).read()
    def status():return json.loads(get('status.json'))
    def connect():
        c=AuditPublisher(socket.create_connection((args.host,9020),timeout=5));c.start();return c
    def receive(task,window,timeout=6):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            with client.audit_lock:value=client.received.pop((task,window),None)
            if value is not None and value.get('input_session')==client.peer.session:return value
            time.sleep(.005)
        raise TimeoutError('missing result '+window)
    def eeg(row,index):
        baseline=row['baseline'];task=row['task'];window='unified:%d'%index
        reference=(dict(kind='SEED_linear',class_id=int(baseline['class_id'])+1,scores=baseline['scores']) if task=='emotion'
            else dict(kind='HGB_regressor',class_id=int(baseline['level']),value=baseline['perclos']))
        assert client.offer_features(task,row['features'],feature_version=PREPROCESSORS[task],window_id=window,
            source='recorded:LEMON:unified',original_reference=reference)
        result=receive(task,window)
        assert result['backend']=='PL_z20_mlp' and result['integer_reference_equal']
        assert result['original_reference']==reference,(result,reference)
        report['eeg_windows']+=1
    try:
        client=connect();initial=status();report['initial']=initial
        assert initial['silent'] and not initial['actuator_control']
        assert not initial['pipeline']['calibration_loaded']
        data=Dataset.load(args.assets_root/'sound/features.npz')
        model=ModelBundle.load((args.models_root or args.assets_root/'models')/'sound')
        for i,values in enumerate(data.x):
            # Live local replay shares the same latest-only sound slot. A newer
            # local window may fence an audit window; retry the same vector with
            # a new ID and retain this scheduling evidence separately.
            for attempt in range(5):
                window='sound-audit:%d:%d'%(i,attempt)
                assert client.offer_features('sound',values,feature_version=PREPROCESSORS['sound'],window_id=window,source='recorded:grouped_sound_audit')
                try:result=receive('sound',window,timeout=1.5);break
                except TimeoutError:
                    report['latest_input_retries'].append(dict(index=i,attempt=attempt,board=status()['counters']))
            else:raise TimeoutError('sound audit repeatedly fenced: %d'%i)
            expected=model.predict(values)
            assert result['model_version']==model.version and result['integer_reference_equal']
            assert result['ps_scores']==expected.scores.tolist()
            report['sound_windows']+=1
        report['sound_model_version']=model.version
        rows=json.loads((args.assets_root/'lemon_features.json').read_text())['records']
        assert client.key_event('key1_long')
        for index,page in enumerate(Navigation.PAGES):
            if index:assert client.key_event('key1_short')
            eeg(rows[index%len(rows)],index)
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                s=status()
                if s['page']!=page:time.sleep(.05);continue
                try:
                    meta=json.loads(get('frame.json'));png=get('frame.png')
                    if meta.get('result',{}).get('page')!=page or hashlib.sha256(png).hexdigest()!=meta['png_sha256']:
                        time.sleep(.1);continue
                    assert meta['display_buffer_equal'] is True
                    folder=args.output.parent/'pages';folder.mkdir(exist_ok=True);(folder/(page+'.png')).write_bytes(png)
                    report['pages'].append(dict(page=page,metadata=meta));break
                except urllib.error.HTTPError:time.sleep(.1)
            else:raise TimeoutError('no verified frame for '+page)
        assert client.key_event('key1_long')
        index,last_sample,last_reconnect=9,time.monotonic(),time.monotonic()
        baseline=status()
        camera=baseline['pipeline']['camera_frames'];frames=baseline['pipeline']['frames']
        deadline=time.monotonic()+args.seconds
        while time.monotonic()<deadline:
            tick=time.monotonic();eeg(rows[index%len(rows)],index);index+=1
            if tick-last_sample>=30:
                s=status();p=s['pipeline']
                assert not p['errors'] and s['counters']['errors']==0
                assert p['frames']==p['display_matches'],'display buffer mismatch'
                assert p['camera_frames']>camera,'no accepted camera snapshot in the last 30s'
                assert p['frames']>frames,'shared display stopped updating'
                assert s['memory']['VmRSS']<256*1024 and s['pending_tasks']<=3
                assert not s['environment']['depth']['valid'] and s['environment']['audio']['payload']['playback_started'] is False
                report['samples'].append(s);last_sample=tick;camera=p['camera_frames'];frames=p['frames'];save()
                print(json.dumps(dict(eeg=report['eeg_windows'],sound=report['sound_windows'],elapsed=report['elapsed_seconds'])),flush=True)
            if tick-last_reconnect>=300:
                client.close();time.sleep(.3);s=status()
                assert all(not s['results'][task]['valid'] for task in ('emotion','fatigue'))
                assert s['results']['sound']['origin']=='local'
                client=connect();report['reconnects']+=1;last_reconnect=tick
            time.sleep(max(0.,1-(time.monotonic()-tick)))
        report['final']=status();report['passed']=True
    except BaseException as exc:
        try:report['failure_snapshot']=status()
        except Exception:pass
        report['errors'].append(type(exc).__name__+': '+str(exc));raise
    finally:
        if client is not None:client.close()
        report['running']=False;save()


if __name__=='__main__':main()
