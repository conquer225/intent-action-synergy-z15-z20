"""Read only EDF header and sparse trigger slices from the five-finger candidate."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
from pathlib import Path
import urllib.request

import numpy as np

URL = 'https://data.nemar.org/on008446/v1.0.0/sub-01/eeg/sub-01_task-random_run-01_eeg.edf'
OUTPUT = Path(__file__).resolve().parent/'output/mi_finger_preflight_20261001/marker_audit.json'


def range_read(start, stop):
    request = urllib.request.Request(URL,headers={'Range':f'bytes={start}-{stop}'})
    with urllib.request.urlopen(request,timeout=30) as response:
        content_range = response.headers.get('Content-Range','')
        if response.status!=206 or not content_range.startswith(f'bytes {start}-{stop}/'):
            raise ValueError('Server range differs; refuse full EEG download')
        payload = response.read(stop-start+2)
    if len(payload)!=stop-start+1:
        raise ValueError('Wrong range length')
    return payload


def fields(payload, width, count):
    return [payload[i*width:(i+1)*width].decode('ascii').strip() for i in range(count)]


def main():
    if OUTPUT.exists():
        raise RuntimeError('Existing marker audit preserved')
    first = range_read(0,255)
    header_bytes = int(first[184:192]); records = int(first[236:244])
    record_seconds = float(first[244:252]); signal_count = int(first[252:256])
    rest = range_read(256,header_bytes-1)
    offset = 0; header = {}
    for key,width in [('labels',16),('transducer',80),('units',8),('physical_min',8),('physical_max',8),
                      ('digital_min',8),('digital_max',8),('prefilter',80),('samples_per_record',8),('reserved',32)]:
        header[key] = fields(rest[offset:offset+width*signal_count],width,signal_count)
        offset += width*signal_count
    if offset!=len(rest):raise ValueError('Unrecognized EDF header layout')
    marker_index = header['labels'].index('Marker')
    counts = np.array(header['samples_per_record'],dtype=int)
    marker_bytes = int(counts[marker_index]*2)
    stride = int(counts.sum()*2)
    marker_offset = int(counts[:marker_index].sum()*2)
    selected = [0,5,10,15,20,25,30,40,60,120,200,900]
    def read_marker(record):
        start = header_bytes+record*stride+marker_offset
        payload = range_read(start,start+marker_bytes-1)
        digital = np.frombuffer(payload,dtype='<i2')
        dmin,dmax = [float(header[k][marker_index]) for k in ('digital_min','digital_max')]
        pmin,pmax = [float(header[k][marker_index]) for k in ('physical_min','physical_max')]
        physical = (digital.astype(float)-dmin)*(pmax-pmin)/(dmax-dmin)+pmin
        codes,counts = np.unique(np.rint(physical).astype(int),return_counts=True)
        return {'record':record,'record_start_seconds':record*record_seconds,
                'bytes_read':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),
                'digital_min':int(digital.min()),'digital_max':int(digital.max()),
                'rounded_physical_codes':dict(zip(codes.astype(str).tolist(),counts.tolist())),
                'within_record_change_samples':np.flatnonzero(np.diff(np.rint(physical))!=0).tolist()}
    with ThreadPoolExecutor(max_workers=6) as pool:
        markers = list(pool.map(read_marker,selected))
    result = {'source_url':URL,'only_header_and_marker_signal_ranges_read':True,
              'eeg_voltage_channels_downloaded':False,'total_bytes_read':header_bytes+len(selected)*marker_bytes,
              'header_sha256':hashlib.sha256(first+rest).hexdigest(),'header_bytes':header_bytes,
              'signal_count':signal_count,'records':records,'record_seconds':record_seconds,
              'recording_duration_seconds':records*record_seconds,'marker_index_zero_based':marker_index,
              'marker_samples_per_record':int(counts[marker_index]),'header':header,'sparse_marker_records':markers,
              'all_markers_or_trials_extracted':False,'candidate_training_ready':False,
              'interpretation':'Sparse EDF trigger samples can check timestamp plausibility; they do not prove all trial labels or MI timing. No automatic event rescaling.',
              'board_accessed':False,'control_enabled':False,'completed_at_local':datetime.now().isoformat()}
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('signal_count','recording_duration_seconds','marker_samples_per_record','total_bytes_read','sparse_marker_records')},indent=2))


if __name__=='__main__':main()
