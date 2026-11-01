"""Read-only export/audit of a bounded live MI capture; no service changes."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

from run_soak_stage import connect

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT/'eeg_apps_z15/output/mi_live_capture_20261003/runtime'
sys.path[:0] = [str(ASSETS), str(ROOT/'pynq_guardianloop')]
from mi_live_capture import PACKET_DTYPE
from mi_eegnet_portable import OfflineEEGNet
from cyton_sqi import CausalEEGFilter
from scipy import signal


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    base='/home/xilinx/mi-live-virtual-20261003-a1/mi-captures/'
    if not args.capture.startswith(base) or '/' in args.capture[len(base):]:
        raise ValueError('Expected one existing diagnostic capture directory')
    args.output.mkdir(parents=True,exist_ok=False)
    client=connect()
    try:
        with client.open_sftp() as sftp:
            for name in ('metadata.json','events.jsonl','packets.bin'):
                sftp.get(args.capture+'/'+name,str(args.output/name))
            lines=(args.output/'events.jsonl').read_text(encoding='utf-8').splitlines()
            # A live writer can leave one trailing partial line in the copied snapshot.
            events=[]
            for i,line in enumerate(lines):
                try: events.append(json.loads(line))
                except json.JSONDecodeError:
                    if i!=len(lines)-1: raise
            candidates=[r for r in events if r['event']=='candidate']
            for row in candidates:
                name=row['trial_id']+'.npz'
                sftp.get(args.capture+'/'+name,str(args.output/name))
    finally: client.close()
    meta=json.loads((args.output/'metadata.json').read_text(encoding='utf-8'))
    packet_bytes=(args.output/'packets.bin').read_bytes()
    raw=np.frombuffer(packet_bytes[:len(packet_bytes)//PACKET_DTYPE.itemsize*PACKET_DTYPE.itemsize],dtype=PACKET_DTYPE)
    model=OfflineEEGNet(ROOT/'eeg_apps_z15/output/mi_cued_delivery_20261002_final/experimental_eegnet.npz',allow_experimental=True)
    model_path=ROOT/'eeg_apps_z15/output/mi_cued_delivery_20261002_final/experimental_eegnet.npz'
    if hashlib.sha256(model_path.read_bytes()).hexdigest()!=meta['model_sha256']:
        raise ValueError('Model identity mismatch')
    starts={r['trial_id']:r for r in events if r['event']=='trial_start'}
    feed=[r for r in events if r['event']=='feed']
    # Exact first feed establishes the sequence at the beginning of stream epoch 1.
    # Refuse interpolation or a guessed mapping if more than one data epoch exists.
    epochs=sorted({r['stream_epoch'] for r in feed})
    continuous=None
    if len(epochs)==1 and feed[0]['index_start']==0:
        first=feed[0]
        ends=np.flatnonzero((raw['sequence']==first['last_sequence']) &
                           (raw['received_monotonic_s']==first['received_monotonic_s']))
        if len(ends)==1:
            initial=int(ends[0])+1-first['index_end_exclusive']
            if initial>=0:
                selected=raw[initial:]
                contiguous=bool(np.all(np.diff(selected['ordinal'])==1) and
                    np.all((selected['sequence'][1:].astype(int)-selected['sequence'][:-1].astype(int))%256==1))
                if contiguous:
                    values=selected['adc'].astype(np.float64)*meta['microvolts_per_count']
                    values-=values.mean(axis=1,keepdims=True)
                    conditioned=CausalEEGFilter().process(values)
                    sos=signal.butter(4,(8,30),fs=250,btype='bandpass',output='sos')
                    continuous=signal.sosfilt(sos,conditioned,axis=0)
    trials=[]
    for row in candidates:
        with np.load(args.output/(row['trial_id']+'.npz'),allow_pickle=False) as saved:
            wave=saved['filtered_uv']
            calculated=model.logits(wave)[0]
            normalized=((wave-model.mean[None,:,None])/model.scale[None,:,None]).astype(np.float32)
            std=np.std(wave[0],axis=1)
            raw_error=None
            if continuous is not None:
                start,stop=int(saved['window_start']),int(saved['window_end_exclusive'])
                raw_error=float(np.max(np.abs(continuous[start:stop].T[None]-wave)))
            trials.append(dict(trial_id=row['trial_id'],target=starts[row['trial_id']]['target'],
                label=row['label'],source=row['source'],logits=row['logits'],
                stream_epoch=int(saved['stream_epoch']),filtered_std_uv=std.tolist(),
                normalized_std=np.std(normalized[0],axis=1).tolist(),
                normalized_exact=bool(np.array_equal(normalized,saved['normalized_fp32'])),
                logit_max_error=float(np.max(np.abs(calculated-np.asarray(row['logits'])))),
                raw_continuous_filter_max_error_uv=raw_error,
                window_start=int(saved['window_start']),window_end_exclusive=int(saved['window_end_exclusive'])))
    report=dict(scope='Read-only diagnostic; not an accuracy experiment or model change',
        capture_directory=args.capture,snapshot_is_closed=meta.get('state')=='closed',
        raw_rows_exported=len(raw),trailing_partial_packet_bytes=len(packet_bytes)%PACKET_DTYPE.itemsize,
        model_sha256=meta['model_sha256'],source_scale=model.scale.tolist(),
        zero_input_logits=model.logits(np.zeros((1,8,500)))[0].tolist(),
        stream_epochs=epochs,continuous_adc_reconstruction=continuous is not None,
        trials=trials,withdrawals=[r for r in events if r['event']=='withdraw'],
        file_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.output.iterdir() if p.is_file()},
        no_service_or_model_or_pl_changes=True,
        limitations=['Capture remains live unless metadata says closed; export is a prefix snapshot',
                    'Prompt receipt alignment is not optical synchronization',
                    'Source normalization mismatch is a diagnostic clue, not a proved cause or an authorization to boost gain'])
    (args.output/'AUDIT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('raw_rows_exported','continuous_adc_reconstruction','trials','source_scale','zero_input_logits')},ensure_ascii=False))


if __name__=='__main__': main()
