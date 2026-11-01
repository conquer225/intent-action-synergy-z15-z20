"""Verified raw Cho2017 downloads and original-order fixed-cap trial decoding."""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
from scipy.io import loadmat

HERE = Path(__file__).resolve().parent
DATA = Path('D:/ican/datasets/Cho2017')
BASE = 'https://s3.ap-northeast-1.wasabisys.com/gigadb-datasets/'
PREFIX = 'live/pub/10.5524/100001_101000/100295/'
FIXED = ('F3', 'F4', 'C3', 'C4', 'T7', 'T8', 'O1', 'O2')
# External channel order is explicit in the preserved MOABB reference loader.
PICKS = (4, 39, 12, 49, 14, 51, 26, 63)


def hashes(path):
    sha, md5 = hashlib.sha256(), hashlib.md5()
    part_digests = []
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(5 * 1024 * 1024), b''):
            sha.update(block)
            md5.update(block)
            part_digests.append(hashlib.md5(block).digest())
    multipart = hashlib.md5(b''.join(part_digests)).hexdigest() + '-' + str(len(part_digests))
    return {'sha256': sha.hexdigest(), 'md5': md5.hexdigest(), 'multipart_5MiB_etag': multipart}


def listing(root=DATA):
    document = ET.parse(root / 'source_docs/gigadb_object_listing.xml').getroot()
    ns = {'s': 'http://s3.amazonaws.com/doc/2006-03-01/'}
    if document.find('s:IsTruncated', ns).text != 'false':
        raise ValueError('Incomplete object listing')
    rows = {}
    for item in document.findall('s:Contents', ns):
        key = item.find('s:Key', ns).text
        name = key.removeprefix(PREFIX)
        rows[name] = {'url': BASE + key, 'bytes': int(item.find('s:Size', ns).text),
                      'etag': item.find('s:ETag', ns).text.strip('"')}
    return rows


def verified_file(path, source):
    if path.stat().st_size != source['bytes']:
        raise ValueError('Object length mismatch: ' + str(path))
    actual = hashes(path)
    etag = source['etag']
    check = actual['multipart_5MiB_etag'] if '-' in etag else actual['md5']
    if check != etag:
        raise ValueError('Object ETag mismatch: ' + str(path))
    return {**source, **actual, 'path': str(path), 'download_verified': True,
            'verification': 'length and remote MD5 ETag (5MiB multipart when applicable); SHA256 is local provenance, not author SHA256'}


def fetch_ranges(partial, source):
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > source['bytes']:
        raise ValueError('Partial exceeds remote object size; preserved without truncation')
    while offset < source['bytes']:
        stop = min(offset + 8 * 1024 * 1024, source['bytes']) - 1
        request = urllib.request.Request(source['url'], headers={'Range': f'bytes={offset}-{stop}'})
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=25) as response:
                    if response.status != 206 or response.headers['Content-Range'] != f'bytes {offset}-{stop}/{source["bytes"]}':
                        raise ValueError('Server did not honor the exact byte range')
                    if response.headers['ETag'].strip('"') != source['etag']:
                        raise ValueError('Remote object changed during download')
                    block = response.read()
                if len(block) != stop - offset + 1:
                    raise ValueError('Incomplete range; not appended')
                break
            except (urllib.error.URLError, TimeoutError):
                if attempt == 1:
                    raise
        with partial.open('ab') as stream:
            if stream.tell() != offset:
                raise ValueError('Partial changed outside this range transfer; preserved without appending')
            stream.write(block)
        offset = stop + 1


def fetch(subject, root, sources, ranged=False):
    name = f's{subject:02d}.mat'
    target = root / name
    source = sources['mat_data/' + name]
    if not target.exists():
        partial = target.with_suffix('.mat.part')
        if not partial.exists() or partial.stat().st_size != source['bytes']:
            if ranged:
                fetch_ranges(partial, source)
            else:
                completed = subprocess.run(['curl.exe', '--fail', '--location', '--silent', '--show-error',
                                            '--retry', '1', '--connect-timeout', '15', '--max-time', '180',
                                            '--continue-at', '-', '--output', str(partial), source['url']],
                                           check=False, capture_output=True, text=True)
                if completed.returncode:
                    raise RuntimeError('Download failed; partial retained: ' + completed.stderr)
        verified_file(partial, source)
        partial.rename(target)
    row = verified_file(target, source)
    row.update(subject=subject, completed_at_local=datetime.now().isoformat())
    return row


@dataclass
class Subject:
    subject: int
    samples: np.ndarray
    labels: np.ndarray
    original_keys: np.ndarray
    class_trial_indices: np.ndarray
    voltage_bad: np.ndarray
    emg_bad: np.ndarray
    cue_sample: int
    rate: int
    fields: list


def annotation_flags(eeg, name, trials):
    entries = np.asarray(getattr(eeg.bad_trial_indices, name), dtype=object).ravel()
    if len(entries) != 2:
        raise ValueError('Expected left/right bad-trial annotation cells')
    result = np.zeros((2, trials), dtype=bool)
    for label, entry in enumerate(entries):
        indices = np.asarray(entry).ravel()
        if not np.isfinite(indices).all() or not np.equal(indices, np.floor(indices)).all():
            raise ValueError('Non-integral bad-trial index')
        if len(indices) and (indices.min() < 1 or indices.max() > trials):
            raise ValueError('Out-of-range MATLAB one-based bad-trial index')
        result[label, indices.astype(int) - 1] = True
    return result.ravel()


def load_subject(subject, root=DATA):
    path = root / f's{subject:02d}.mat'
    verified_file(path, listing(root)['mat_data/' + path.name])
    reference = ast.parse((root / 'source_docs/moabb_gigadb_reference.py').read_text(encoding='utf-8'))
    name_lists = [ast.literal_eval(node.value) for node in ast.walk(reference)
                  if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                  and target.id == 'eeg_ch_names' for target in node.targets)]
    if len(name_lists) != 1 or len(name_lists[0]) != 64 or tuple(name_lists[0][i] for i in PICKS) != FIXED:
        raise ValueError('Preserved external channel order does not match fixed picks')
    eeg = loadmat(path, squeeze_me=True, struct_as_record=False)['eeg']
    rate, count = int(eeg.srate), int(eeg.n_imagery_trials)
    if rate != 512 or count not in (100, 120) or not np.array_equal(eeg.frame, [-2000, 5000]):
        raise ValueError('Unexpected rate/count/frame: ' + path.name)
    length = 7 * rate
    event = np.asarray(eeg.imagery_event)
    if event.shape != (count * length,) or not set(np.unique(event)).issubset({0, 1}):
        raise ValueError('Invalid imagery event vector')
    events = np.flatnonzero(event == 1)
    if len(events) != count or not np.array_equal(events // length, np.arange(count)):
        raise ValueError('Exactly one cue per 7s trial required')
    cue_offsets = events % length
    if len(np.unique(cue_offsets)) != 1 or abs(int(cue_offsets[0]) - 2 * rate) > 1:
        raise ValueError('Cue event is inconsistent with supplied frame')
    left, right = np.asarray(eeg.imagery_left), np.asarray(eeg.imagery_right)
    if any(x.shape != (68, count * length) for x in (left, right)):
        raise ValueError('Unexpected EEG+EMG dimensions')
    samples = np.concatenate([x[list(PICKS)].T.reshape(count, length, 8) for x in (left, right)])
    if not np.isfinite(samples).all():
        raise ValueError('Non-finite fixed-cap sample; refused silent trial removal')
    with zipfile.ZipFile(root / 'source_docs/trial_sequence.zip') as archive:
        sequence = loadmat(io.BytesIO(archive.read(f's{subject}_trial_sequence_v1.mat')),
                           squeeze_me=True, struct_as_record=False)['trial_sequence']
    keys = [np.asarray(getattr(sequence, name)).ravel() for name in ('imagery_left', 'imagery_right')]
    if any(x.shape != (count,) or not np.all(np.diff(x.astype(np.int64)) > 0) for x in keys):
        raise ValueError('Trial sequence cannot be aligned to original class-specific order')
    original = np.concatenate(keys).astype(np.int64)
    if len(np.unique(original)) != 2 * count:
        raise ValueError('Duplicated original trial ordering key')
    order = np.argsort(original)
    labels = np.repeat([0, 1], count)
    class_index = np.tile(np.arange(count), 2)
    voltage = annotation_flags(eeg, 'bad_trial_idx_voltage', count)
    emg = annotation_flags(eeg, 'bad_trial_idx_mi', count)
    return Subject(subject, samples[order], labels[order], original[order], class_index[order],
                   voltage[order], emg[order], int(cue_offsets[0]), rate, list(eeg._fieldnames))


def audit(subject, root):
    item = load_subject(subject, root)
    sources = listing(root)
    row = verified_file(root / f's{subject:02d}.mat', sources[f'mat_data/s{subject:02d}.mat'])
    centered = item.samples.astype(np.float64) - item.samples[:, :1]
    output = {**row, 'subject': subject, 'fields': item.fields, 'channels': FIXED,
              'zero_based_picks': PICKS, 'raw_channels': 68, 'eeg_channels': 64, 'emg_channels': 4,
              'fixed_sample_shape': list(item.samples.shape), 'labels_0_left_1_right': np.bincount(item.labels).tolist(),
              'rate_hz': item.rate, 'trial_seconds': 7, 'cue_sample_zero_based': item.cue_sample,
              'nominal_frame_ms': [-2000, 5000], 'cue_offset_from_nominal_samples': item.cue_sample - 2 * item.rate,
              'author_voltage_flag_count': int(item.voltage_bad.sum()),
              'author_emg_flag_count': int(item.emg_bad.sum()), 'trials_discarded': 0,
              'first20_original_labels': item.labels[:20].tolist(),
              'first20_original_order_keys': item.original_keys[:20].tolist(),
              'raw_absolute_p99': float(np.quantile(np.abs(item.samples), .99)),
              'first_sample_centered_absolute_p99': float(np.quantile(np.abs(centered), .99)),
              'units': 'microvolts according to maintained MOABB loader x1e-6 for MNE volts; MAT lacks explicit unit tag',
              'original_keys_semantics': 'author trial_sequence ascending keys used only for order; not claimed to be verified run IDs or absolute time',
              'source_structure': 'class-separated concatenated 7s epochs, not continuous session',
              'classifier_fitted': False, 'cyton_transfer_validated': False,
              'source_doc_hashes': {p.name: hashes(p)['sha256'] for p in (root / 'source_docs').iterdir() if p.is_file()}}
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('download', 'audit'))
    parser.add_argument('--root', type=Path, default=DATA)
    parser.add_argument('--subjects', type=int, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--ranged', action='store_true', help='Exact bounded byte-range transfers for stalled full GETs')
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError('Existing manifest preserved: ' + str(args.output))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    people = args.subjects or [1]
    if len(set(people)) != len(people) or any(x < 1 or x > 52 for x in people):
        raise ValueError('Distinct subject IDs 1..52 required')
    if args.action == 'audit':
        result = [audit(person, args.root) for person in people]
    else:
        sources = listing(args.root)
        needed = sum(sources[f'mat_data/s{x:02d}.mat']['bytes']
                     for x in people if not (args.root / f's{x:02d}.mat').exists())
        if shutil.disk_usage(args.root).free < needed + 2 * 1024 ** 3:
            raise RuntimeError('Insufficient free space with 2GiB reserve')
        result = []
        failures = []
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(fetch, person, args.root, sources, args.ranged): person for person in people}
            for future in as_completed(futures):
                try:
                    result.append(future.result())
                except (RuntimeError, ValueError, urllib.error.URLError, TimeoutError) as error:
                    failures.append({'subject': futures[future], 'error': str(error)})
                    print('FAILED', futures[future], str(error), flush=True)
                    continue
                args.output.write_text(json.dumps(sorted(result, key=lambda r: r['subject']), indent=2) + '\n', encoding='utf-8')
                print('VERIFIED', futures[future], len(result), '/', len(people), flush=True)
        if failures:
            failure_path = args.output.with_suffix('.failures.json')
            failure_path.write_text(json.dumps(failures, indent=2) + '\n', encoding='utf-8')
            raise RuntimeError('Incomplete download; verified files retained, see ' + str(failure_path))
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print('SAVED', str(args.output), flush=True)


if __name__ == '__main__':
    main()
