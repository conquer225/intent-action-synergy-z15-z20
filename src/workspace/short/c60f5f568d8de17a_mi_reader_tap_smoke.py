"""Linux pipe + real ARM model check; synthetic replay, no USB or PL access."""
import argparse
import json
import os
from pathlib import Path
import threading
import time
from urllib.request import Request, urlopen

import numpy as np

from cyton_guardianloop import DEFAULT_UV_PER_COUNT, decode_eeg_counts, packets
from mi_acquisition import MICandidateRuntime
from mi_cued import CuedMISession
from mi_eegnet_portable import OfflineEEGNet
from mi_eegnet_rms import OfflineEEGNet as RMSEEGNet
from mi_features import CHANNELS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--shared-rms', action='store_true')
    args = parser.parse_args()
    counts = np.rint(600 * np.sin(2*np.pi*np.arange(2000)[:,None]/250 * np.arange(8,16))).astype(np.int32)
    runtime = MICandidateRuntime(args.model, CHANNELS, source='replay', host='127.0.0.1',
        port=0, log_path=None, status_paths={}, packet_decoder=decode_eeg_counts,
        microvolts_per_count=DEFAULT_UV_PER_COUNT)
    url = 'http://127.0.0.1:%s' % runtime.server.server_port
    def request(body=None):
        req = Request(url+'/api/mi-cue', data=None if body is None else json.dumps(body).encode(),
                      headers={'Content-Type':'application/json', 'Origin':url})
        with urlopen(req, timeout=2) as response:
            return json.load(response)
    r,w = os.pipe()
    stopped = threading.Event()
    def write_fixture():
        started = time.monotonic()
        for index, row in enumerate(counts):
            if stopped.is_set():
                return
            frame = bytes((0xa0,index%256)) + b''.join(int(x).to_bytes(3,'big',signed=True) for x in row)
            os.write(w, frame+bytes(6)+bytes((0xc0,)))
            time.sleep(max(0, started+(index+1)/250-time.monotonic()))
    writer = threading.Thread(target=write_fixture)
    reader = packets(r, 2, with_timing=True, packet_sink=runtime.reader_sink)
    try:
        writer.start()
        next(reader)  # Start the serial process; deliberately never consume more primary packets.
        deadline = time.monotonic()+5
        while request()['input_state'] != 'ready':
            if time.monotonic()>deadline:
                raise AssertionError('Independent reader tap failed to warm up')
            time.sleep(.1)
        trial = request(dict(action='start', target='right', virtual_control=True))['id']
        request(dict(action='presented', id=trial, browser_onset_ms=1, browser_send_ms=2))
        deadline = time.monotonic()+4
        while True:
            state = request(dict(action='heartbeat', id=trial))
            if state['result'] is not None:
                break
            if state['state'] != 'active' or time.monotonic()>deadline:
                raise AssertionError('Tap inference failed: '+json.dumps(state))
            time.sleep(.1)
        candidate = state['result']
        end = candidate['window_end_exclusive']
        reference = CuedMISession(source='replay')
        for first in range(0, end, 50):
            reference.feed(counts[first:first+50].astype(np.float64)*DEFAULT_UV_PER_COUNT,
                           np.arange(first,first+50)%256, received_monotonic=time.monotonic())
        offset = reference.index-len(reference.filtered)
        window = reference.filtered[candidate['window_start']-offset:end-offset]
        model_type = RMSEEGNet if args.shared_rms else OfflineEEGNet
        expected = model_type(args.model,allow_experimental=True).logits(window.T[None])[0]
        np.testing.assert_allclose(candidate['logits'], expected, rtol=0, atol=1e-12)
        assert state['virtual_hand']['command_count']==1
        final = request(dict(action='stop', id=trial))
        assert final['result'] is None and not final['virtual_hand']['enabled']
        result = dict(passed=True, synthetic_fixture=True, source='replay', accuracy_scored=False,
                      primary_paused=True, warmed_up=True, inference_equal_reference=True,
                      virtual_command_once=True, stop_withdrawn=True, hardware_control=False,
                      candidate=candidate, max_logit_error=float(np.max(np.abs(expected-candidate['logits']))))
    finally:
        stopped.set(); writer.join(timeout=2)
        reader.close(); os.close(r); os.close(w)
        runtime.close()
    assert not writer.is_alive() and not runtime.thread.is_alive()
    args.output.write_text(json.dumps(result,indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
