"""Check one event table against independent sparse EDF marker samples."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import urllib.request

import numpy as np
from mi_finger_marker_audit import range_read

HERE = Path(__file__).resolve().parent
RUN = HERE/'output/mi_finger_preflight_20261001'
URL = 'https://data.nemar.org/on008446/v1.0.0/sub-01/eeg/sub-01_task-random_run-01_events.tsv'
EXPECTED_HASH = '336c6c7963d975667765d3cbc87077f89ea7471a585aa46f70d99bbc3649e2ce'


def transition_rows(onsets, codes):
    starts = np.r_[0,np.flatnonzero(np.diff(codes)!=0)+1]
    stops = np.r_[starts[1:],len(codes)]
    return [{'start_seconds':float(onsets[start]),'stop_seconds':float(onsets[stop-1]+1/512),
             'duration_seconds':float((stop-start)/512),'code':int(codes[start]),'rows':int(stop-start)}
            for start,stop in zip(starts,stops)]


def main():
    destination = RUN/'event_timing_audit.json'
    if destination.exists():raise RuntimeError('Existing timing audit preserved')
    marker = json.loads((RUN/'marker_audit.json').read_text(encoding='utf-8'))
    with urllib.request.urlopen(URL,timeout=30) as response:
        payload = response.read(12000000)
    digest = hashlib.sha256(payload).hexdigest()
    if len(payload)!=11179696 or digest!=EXPECTED_HASH:
        raise ValueError('Event data changed from the pinned Git annex identity')
    values = np.loadtxt(io.BytesIO(payload),delimiter='\t',skiprows=1)
    onsets,codes = values[:,0],values[:,2].astype(int)
    if not np.all(values[:,1]==0) or not np.all(values[:,2]==codes):
        raise ValueError('Event durations or codes differ')
    # This mapping is a tested hypothesis, not a correction applied to training.
    scaled = onsets*512
    sample_indices = np.rint(scaled*512).astype(int)
    inferred_indices = np.arange(5120,5120+len(values))
    np.testing.assert_array_equal(sample_indices,inferred_indices)
    marker_index = marker['marker_index_zero_based']; header = marker['header']
    counts = np.array(header['samples_per_record'],dtype=int)
    stride = int(counts.sum()*2); offset = int(counts[:marker_index].sum()*2)
    dmin,dmax = [float(header[k][marker_index]) for k in ('digital_min','digital_max')]
    pmin,pmax = [float(header[k][marker_index]) for k in ('physical_min','physical_max')]
    records = [r['record'] for r in marker['sparse_marker_records'] if r['record']>=10]
    def compare(record):
        start = marker['header_bytes']+record*stride+offset
        data = range_read(start,start+1023)
        digital = np.frombuffer(data,dtype='<i2')
        actual = np.rint((digital.astype(float)-dmin)*(pmax-pmin)/(dmax-dmin)+pmin).astype(int)
        first = record*512-5120
        expected = codes[first:first+512]
        np.testing.assert_array_equal(actual,expected)
        return {'record_seconds':record,'samples_checked':512,'marker_codes_exactly_match_scaled_events':True,
                'marker_sha256':hashlib.sha256(data).hexdigest()}
    with ThreadPoolExecutor(max_workers=6) as pool:
        matched = list(pool.map(compare,records))
    transitions = transition_rows(sample_indices/512,codes)
    cues = [row for row in transitions if row['code'] in (3,4,5,6,7)]
    report = {'event_url':URL,'event_sha256':digest,'event_bytes_read':len(payload),
              'event_rows':len(values),'as_published_onset_range_seconds':[float(onsets[0]),float(onsets[-1])],
              'as_published_duration_all_zero':True,'tested_mapping':'published_onset_seconds times512; round to nearest native512Hz sample',
              'scaled_onset_range_seconds':[float(scaled[0]),float(scaled[-1])],
              'native_sample_rounding_max_abs_error_seconds':float(np.max(np.abs(scaled-sample_indices/512))),
              'every_table_row_maps_to_one_consecutive_sample':True,'independent_sparse_EDF_records':matched,
              'independent_marker_samples_checked':sum(r['samples_checked'] for r in matched),
              'transitions_after_deduplication':transitions,'five_finger_cue_intervals':len(cues),
              'finger_cue_counts':{str(code):sum(r['code']==code for r in cues) for code in range(3,8)},
              'all_candidate_recordings_verified':False,'all_EDF_markers_verified':False,
              'correction_applied_to_training':False,'candidate_training_ready':False,
              'limitation':'One recording only. Timescale issue and repeated sample rows are supported by5120 independent marker samples; the complete corpus, task instructions, cue/MI timing and hand laterality still require verification.',
              'eeg_voltage_channels_downloaded':False,'board_accessed':False,'control_enabled':False,
              'completed_at_local':datetime.now().isoformat()}
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('event_rows','scaled_onset_range_seconds','native_sample_rounding_max_abs_error_seconds','independent_marker_samples_checked','five_finger_cue_intervals','finger_cue_counts','candidate_training_ready')},indent=2))


if __name__=='__main__':main()
