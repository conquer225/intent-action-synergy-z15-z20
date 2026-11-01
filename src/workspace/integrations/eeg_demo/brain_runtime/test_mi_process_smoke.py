"""Real spawned-worker plumbing/crash check with synthetic input, not accuracy."""
import argparse
import json
from pathlib import Path
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

import numpy as np

from mi_acquisition import MICandidateRuntime
from cyton_reader_sink import decode_eeg_counts
from mi_features import CHANNELS


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reader-tap-batch',action='store_true')
    args=parser.parse_args()
    out=args.output.resolve();out.mkdir(exist_ok=False)
    runtime=MICandidateRuntime(args.model,CHANNELS,source='replay',host='127.0.0.1',
                               port=0,log_path=out/'events.jsonl',status_paths={},
                               packet_decoder=decode_eeg_counts if args.reader_tap_batch else None,
                               microvolts_per_count=.022,
                               reader_batch_samples=10 if args.reader_tap_batch else 1)
    url='http://127.0.0.1:'+str(runtime.server.server_port)
    def request(body=None):
        req=Request(url+'/api/mi-cue',data=None if body is None else json.dumps(body).encode(),
                    headers={'Content-Type':'application/json','Origin':url})
        with urlopen(req,timeout=2) as response:
            return json.load(response)
    def feed(start,n):
        for first in range(start,start+n,50):
            indices=np.arange(first,first+50)
            wave=10*np.sin(2*np.pi*indices[:,None]/250*np.arange(8,16)[None])
            for i,row in zip(indices,wave):
                if args.reader_tap_batch:
                    counts=np.rint(row/.022).astype(np.int32)
                    packet=bytes((0xa0,int(i%256)))+b''.join(
                        (int(v)&0xffffff).to_bytes(3,'big') for v in counts)+bytes(6)+bytes((0xc0,))
                    assert runtime.reader_sink.offer(packet,0,time.monotonic())
                else:
                    runtime.adapter.packet(row,int(i%256),False,received_at=time.monotonic())
            if args.reader_tap_batch:
                assert runtime.reader_sink.flush()
                deadline=time.monotonic()+2
                while request()['received_samples'] != first+50:
                    if time.monotonic() >= deadline:
                        raise AssertionError('Grouped tap failed to drain a fresh 50-sample batch')
                    time.sleep(.01)
            else:
                runtime.adapter.pending.join()
    try:
        feed(0,750)
        assert request()['input_state']=='ready'
        trial=request(dict(action='start',target='left'))['id']
        request(dict(action='presented',id=trial,browser_onset_ms=1,browser_send_ms=2))
        feed(750,650)
        candidate=request()['result']
        assert candidate is not None and not candidate['control_enabled']
        assert candidate['window_end_exclusive']-candidate['window_start']==500
        # Terminate only this test's spawned PC worker, never a board process.
        runtime.thread.terminate();runtime.thread.join(timeout=3)
        assert not runtime.thread.is_alive()
        if not args.reader_tap_batch:
            feed(1400,50)
            assert runtime.adapter.error is not None
        final=runtime.session.snapshot()
        assert final['result'] is None and final['input_state']=='no_data'
        try:
            request()
        except URLError:
            endpoint_stopped=True
        else:
            raise AssertionError('Dead worker left a responding endpoint')
        result=dict(passed=True,synthetic_fixture=True,accuracy_scored=False,
                    spawned_worker_inference=True,crash_withdrawal=True,endpoint_stopped=endpoint_stopped,
                    reader_tap_batch=args.reader_tap_batch,
                    adapter_error=runtime.adapter.error if runtime.adapter is not None else None,final=final)
    finally:
        runtime.close()
    result['all_workers_stopped']=not runtime.thread.is_alive() and (
        runtime.adapter is None or not runtime.adapter.worker.is_alive())
    assert result['all_workers_stopped']
    (out/'checks.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    main()
