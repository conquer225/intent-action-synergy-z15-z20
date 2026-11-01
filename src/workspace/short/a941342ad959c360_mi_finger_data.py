"""Pinned ds008446 files, native EDF decoding and independently checked trials."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import time
import urllib.error
import urllib.request

import numpy as np

from mi_finger_dataset_preflight import COMMIT, RAW, FIXED, fetch
from mi_physionet_download import sha256_file

HERE = Path(__file__).resolve().parent
RUN = HERE / 'output/mi_finger_baseline_20261001'
ROOT = Path('D:/ican/datasets/ds008446')
MIRROR = 'https://data.nemar.org/on008446/v1.0.0/'
FINGERS = ['thumb', 'index', 'middle', 'ring', 'little']
WIDTHS = [('labels',16),('transducer',80),('units',8),('physical_min',8),
          ('physical_max',8),('digital_min',8),('digital_max',8),('prefilter',80),
          ('samples_per_record',8),('reserved',32)]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    os.replace(temporary, path)


def stems():
    return [f'sub-{p:02d}/eeg/sub-{p:02d}_task-{task}_run-{r:02d}'
            for p in range(1,21) for task in ('random','sequential') for r in (1,2)]


def freeze_protocol():
    path = RUN / 'protocol.json'
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    people = [f'sub-{p:02d}' for p in range(1,21)]
    ranked = sorted(people, key=lambda p: hashlib.sha256(f'finger-20261001:{p}'.encode()).digest())
    confirm = sorted(ranked[:4]); development = sorted(ranked[4:])
    old = json.loads((HERE/'output/mi_model_comparison_20261001/protocol.json').read_text(encoding='utf-8'))
    config = dict(old['eegnet'])
    config.update(epochs_max=100, early_stop_patience=15, seeds=[42,43,44],
                  loss='five-class cross entropy', target_adaptation=False,
                  standardization='channel mean/std from12 fitting people only; frozen for validation and target')
    protocol = dict(dataset='ds008446', pinned_commit=COMMIT, channels=FIXED,
        status='frozen_before_waveform_extraction_or_classifier_scores', development_people=development,
        hypothesis='Fixed8 causal bandpower/ERD or EEGNet can classify five random finger cues above20% across unseen development people; weak BA or strong precue/time-only controls falsify practical intent-decoding readiness.',
        confirmation_people=confirm, confirmation_waveforms_extracted=False,
        confirmation_rule='First4 SHA256 raw digest order of finger-20261001:sub-ID; remaining16 development',
        primary_task='random', sequential_task='audit only, no classification this round',
        labels=FINGERS, chance_balanced_accuracy=0.2,
        fold_rule='LOSO16 development people; non-target SHA256 of finger-fold-20261001:target:source; first3 validation, remaining12 fitting',
        window_seconds=[1,3], baseline_seconds=[-3,-1], precue_control_seconds=[-2,0],
        preprocessing='Native512Hz continuous causal notch50Hz Q30, Butterworth4 1-40Hz; retain linked-mastoid reference (no CAR). Completed2s windows resample_poly125/256 to250Hz with Kaiser5 antialias and constant boundary padding, then no future samples; EEGNet input additionally continuous causal Butterworth4 8-30Hz. This is not yet a numerical match to Cyton/PYNQ.',
        methods=['bandpower_ERD_LDA','EEGNet5'],
        diagnostics=['LDA motor4 F3,F4,C3,C4 subset','LDA O1,O2-only subset','LDA precue fixed8','source-only trial-index majority lookup'],
        bands=[[8,12],[12,18],[18,24],[24,30]],
        eegnet=config, compute=old['compute'],
        primary_metric='Mean16 target-person balanced accuracy; EEGNet average all3 seeds per person',
        secondary_metrics=['macro-F1','five-class confusion','complete trial coverage','PC inference seconds'],
        trial_policy='Every complete cue retained; no amplitude-based or target-score-based deletion; report clipping and amplitude separately',
        bootstrap={'seed':20261001,'draws':10000},
        continuation_gate={'mean_ba_at_least':0.35,'EEGNet_gain_over_LDA_at_least':0.03,'paired_ci_lower_greater_than':0},
        interpretation='Exploratory finger cue-label classification in author-labelled imagery task. Detailed instructions, hand laterality and absence of overt movement unverified; image confound remains even if controls are weak.',
        promotion_gate_passed=False, control_enabled=False, board_accessed=False)
    write_json(path, protocol)
    print('PROTOCOL frozen; confirmation excluded: '+','.join(confirm), flush=True)
    return protocol


def annex_identity(path):
    pointer = fetch(RAW+path).decode('utf-8')
    identities = re.findall(r'SHA256E-s(\d+)--([0-9a-f]{64})\.[a-z]+',pointer)
    if not identities or len(set(identities)) != 1:
        raise ValueError('Unrecognized annex identity: '+path)
    size, digest = identities[0]
    return dict(path=path, bytes=int(size), sha256=digest)


def download_file(entry):
    path = ROOT/entry['path']; path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.stat().st_size != entry['bytes'] or sha256_file(path) != entry['sha256']:
            raise ValueError('Existing file hash mismatch: '+str(path))
        return entry
    part = path.with_suffix(path.suffix+'.part')
    for attempt in range(4):
        offset = part.stat().st_size if part.exists() else 0
        if offset > entry['bytes']:
            raise ValueError('Oversized partial file: '+str(part))
        try:
            if offset < entry['bytes']:
                headers = {'User-Agent':'GuardianLoop-finger-audit'}
                if offset: headers['Range'] = f'bytes={offset}-'
                # A distinct query prevents a prior sparse-range cache from masquerading as a full file.
                request = urllib.request.Request(MIRROR+entry['path']+'?download=full',headers=headers)
                with urllib.request.urlopen(request, timeout=30) as response:
                    if offset:
                        if response.status != 206 or not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):
                            raise ValueError('Resume range not honored: '+entry['path'])
                    elif response.status != 200:
                        raise ValueError('Full-file request returned partial content: '+entry['path'])
                    with part.open('ab' if offset else 'wb') as handle:
                        for chunk in iter(lambda: response.read(1024*1024), b''):
                            handle.write(chunk)
            if part.stat().st_size != entry['bytes'] or sha256_file(part) != entry['sha256']:
                raise ValueError('Downloaded length or SHA mismatch: '+entry['path'])
            os.replace(part,path)
            return entry
        except (OSError, urllib.error.URLError):
            if attempt == 3: raise
            time.sleep(attempt+1)
    raise AssertionError('Unreachable')


def header(path):
    with path.open('rb') as handle:
        first = handle.read(256)
        size = int(first[184:192]); n = int(first[252:256])
        rest = handle.read(size-256)
    if len(first+rest) != size or size != 256*(n+1):
        raise ValueError('Unsupported EDF header length')
    result = dict(header_bytes=size, records=int(first[236:244]), record_seconds=float(first[244:252]), signals=n)
    offset = 0
    for key,width in WIDTHS:
        result[key] = [rest[offset+i*width:offset+(i+1)*width].decode('ascii').strip() for i in range(n)]
        offset += width*n
    counts = np.array(result['samples_per_record'], dtype=int)
    if len(set(counts)) != 1 or result['records'] <= 0 or result['record_seconds'] <= 0:
        raise ValueError('Unequal samples or invalid record duration')
    result['fs'] = int(counts[0])/result['record_seconds']
    result['samples_per_signal_record'] = int(counts[0])
    expected = size+result['records']*sum(counts)*2
    if path.stat().st_size != expected:
        raise ValueError('EDF file size does not match header')
    if len(set(result['labels'])) != n: raise ValueError('Duplicate EDF labels')
    return result


def read_signals(path, info, names):
    count = info['samples_per_signal_record']
    samples = np.memmap(path, mode='r', dtype='<i2', offset=info['header_bytes'],
                        shape=(info['records'],info['signals'],count))
    indexes = [info['labels'].index(name) for name in names]
    digital = np.asarray(samples[:,indexes,:]).transpose(1,0,2).reshape(len(names),-1).copy()
    physical = []
    for values,index in zip(digital,indexes):
        d0,d1 = (float(info[key][index]) for key in ('digital_min','digital_max'))
        p0,p1 = (float(info[key][index]) for key in ('physical_min','physical_max'))
        if d1 <= d0 or p1 <= p0: raise ValueError('Invalid EDF scale')
        physical.append((values.astype(np.float64)-d0)*(p1-p0)/(d1-d0)+p0)
    return np.stack(physical), digital


def transitions(codes, fs):
    starts = np.r_[0,np.flatnonzero(np.diff(codes)) + 1]
    stops = np.r_[starts[1:],len(codes)]
    return [dict(start_sample=int(a), stop_sample=int(b), start_seconds=float(a/fs),
                 duration_seconds=float((b-a)/fs), code=int(codes[a])) for a,b in zip(starts,stops)]


def validate_events(path, native, fs):
    values = np.loadtxt(path, skiprows=1, delimiter='\t')
    if values.ndim != 2 or values.shape[1] != 3 or not np.all(values[:,1] == 0):
        raise ValueError('Unexpected event table layout/durations')
    codes = values[:,2].astype(int)
    if not np.all(values[:,2] == codes): raise ValueError('Noninteger event codes')
    tested = []
    for scale in (1,fs):
        indexes = np.rint(values[:,0]*scale*fs).astype(int)
        consecutive = np.array_equal(indexes,np.arange(indexes[0],indexes[0]+len(indexes)))
        in_range = indexes[0]>=0 and indexes[-1]<len(native)
        matches = in_range and consecutive and np.array_equal(native[indexes],codes)
        tested.append((scale,matches,indexes))
    passing = [(scale,indexes) for scale,matches,indexes in tested if matches]
    if len(passing) != 1: raise ValueError('No unique verified event timescale: '+str(path))
    scale,indexes = passing[0]
    suffix=native[indexes[-1]+1:]
    if not np.all(suffix==0) or len(suffix)>=fs or not np.all(native[:indexes[0]]==0):
        raise ValueError('Events do not cover all nonzero native markers')
    return dict(rows=len(values), onset_multiplier=float(scale), first_native_sample=int(indexes[0]),
                all_published_rows_match_native_marker=True, durations_derived_from_marker=True,
                trailing_zero_marker_samples_outside_events=int(len(suffix)),
                maximum_rounding_error_seconds=float(np.max(abs(values[:,0]*scale-indexes/fs))))


def audit_run(stem):
    path = ROOT/(stem+'_eeg.edf'); info = header(path)
    if info['fs'] != 512 or any(name not in info['labels'] for name in FIXED):
        raise ValueError('Sampling/montage mismatch: '+stem)
    if any(info['units'][info['labels'].index(name)] not in ('uV','µV') for name in FIXED):
        raise ValueError('Unrecognized voltage unit: '+stem)
    physical,_ = read_signals(path, info, ['Marker'])
    native = np.rint(physical[0]).astype(int)
    if not set(native).issubset(set(range(8))) or np.max(abs(physical[0]-native)) > 0.001:
        raise ValueError('Unexpected native marker values: '+stem)
    checked = validate_events(ROOT/(stem+'_events.tsv'),native,info['fs'])
    intervals = transitions(native,info['fs']); cues = [r for r in intervals if 3<=r['code']<=7]
    if not cues or any(r['duration_seconds'] < 3 for r in cues): raise ValueError('Incomplete finger cues')
    sequence = [r['code'] for r in cues]
    return dict(stem=stem, person=stem.split('/')[0], task='random' if '_task-random_' in stem else 'sequential',
                fs=info['fs'], signals=info['signals'], seconds=info['records']*info['record_seconds'],
                reference_from_metadata='linked mastoids', fixed8_units='uV',
                marker_rounding_error=float(np.max(abs(physical[0]-native))), events=checked,
                cue_counts={name:sequence.count(code) for name,code in zip(FINGERS,range(3,8))},
                cue_sequence_sha256=hashlib.sha256(bytes(sequence)).hexdigest(), intervals=intervals)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers',type=int,default=4)
    args = parser.parse_args()
    freeze_protocol()
    manifest_path = RUN/'download_manifest.json'
    if manifest_path.exists():
        entries = json.loads(manifest_path.read_text(encoding='utf-8'))['files']
    else:
        names = [s+suffix for s in stems() for suffix in ('_eeg.edf','_events.tsv')]
        with ThreadPoolExecutor(max_workers=8) as pool: entries = list(pool.map(annex_identity,names))
        write_json(manifest_path,dict(commit=COMMIT, mirror=MIRROR, files=entries))
    ROOT.mkdir(parents=True, exist_ok=True)
    needed = sum(e['bytes'] for e in entries if not (ROOT/e['path']).exists())
    if shutil.disk_usage(ROOT).free < needed+2*1024**3: raise ValueError('Insufficient disk reserve')
    print(f'DOWNLOAD {len(entries)} files, {needed/1024**3:.2f} GiB needed; no CSV or video',flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(download_file,e) for e in entries]
        for i,future in enumerate(as_completed(futures),1):
            entry = future.result()
            print(f'VERIFIED {i}/{len(entries)} {entry["path"]}',flush=True)
    records = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,row in enumerate(pool.map(audit_run,stems()),1):
            records.append(row)
            print(f'AUDITED {i}/80 {row["stem"]} cues={sum(row["cue_counts"].values())}',flush=True)
    metadata = {}
    names = ['README.md','dataset_description.json','sourcedata/counterbalancing_log.json']+[s+'_eeg.json' for s in stems()]
    with ThreadPoolExecutor(max_workers=8) as pool:
        payloads = list(pool.map(lambda name:(name,fetch(RAW+name)),names))
    for name,payload in payloads:
        destination = ROOT/name; destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists() and destination.read_bytes()!=payload: raise ValueError('Metadata changed')
        destination.write_bytes(payload)
        metadata[name] = dict(sha256=hashlib.sha256(payload).hexdigest(),text=payload.decode('utf-8'))
    duplicates = {}
    for entry in entries:
        if entry['path'].endswith('.edf'): duplicates.setdefault(entry['sha256'],[]).append(entry['path'])
    report = dict(all_80_runs_native_markers_checked=True, all_160_files_sha256_verified=True,
                  total_download_bytes=sum(e['bytes'] for e in entries), records=records,
                  duplicate_edf_files=[v for v in duplicates.values() if len(v)>1], metadata=metadata,
                  no_confirmation_EEG_waveforms_extracted=True, board_accessed=False, control_enabled=False)
    write_json(RUN/'data_audit.json',report)
    print('DATA AUDIT COMPLETE',flush=True)


if __name__=='__main__': main()
