"""Metadata-only inspection of a public five-finger MI candidate; no EEG download."""
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import urllib.request

COMMIT = '8d8448e2dcd731b251f2f3c85b98cce5847cb000'
RAW = f'https://raw.githubusercontent.com/OpenNeuroDatasets/ds008446/{COMMIT}/'
FIXED = ['F3','F4','C3','C4','T7','T8','O1','O2']
OUTPUT = Path(__file__).resolve().parent/'output/mi_finger_preflight_20261001'


def fetch(url):
    request = urllib.request.Request(url,headers={'User-Agent':'GuardianLoop-metadata-audit'})
    with urllib.request.urlopen(request,timeout=20) as response:
        payload = response.read(1000000)
    if len(payload)>=1000000:
        raise ValueError('Unexpectedly large metadata; do not download EEG')
    return payload


def inspect_channels(path):
    payload = fetch(RAW+path)
    rows = list(csv.DictReader(io.StringIO(payload.decode('utf-8')),delimiter='\t'))
    by_name = {row['name']:row for row in rows}
    if len(by_name)!=len(rows):
        raise ValueError('Duplicate channel names: '+path)
    missing = [name for name in FIXED if name not in by_name or by_name[name]['type']!='EEG']
    return {'path':path,'sha256':hashlib.sha256(payload).hexdigest(),
            'missing_fixed_channels':missing,'fixed_rows':[by_name[name] for name in FIXED if name in by_name],
            'total_channel_rows':len(rows)}


def event_range(tail=False):
    url = 'https://data.nemar.org/on008446/v1.0.0/sub-01/eeg/sub-01_task-random_run-01_events.tsv'
    request = urllib.request.Request(url,headers={'Range':'bytes=-4096' if tail else 'bytes=0-4095'})
    with urllib.request.urlopen(request,timeout=20) as response:
        if response.status!=206:
            raise ValueError('Range access required; refuse full event download')
        content_range = response.headers.get('Content-Range')
        payload = response.read(4096)
    text = payload.decode('utf-8')
    if tail:
        lines = text.splitlines()[1:]
        header = 'onset\tduration\ttrial_type\n'
        text = header+'\n'.join(lines)+'\n'
    else:
        text = text[:text.rfind('\n')+1]
    rows = list(csv.DictReader(io.StringIO(text),delimiter='\t'))
    onsets = [float(row['onset']) for row in rows]
    return {'url':url,'content_range':content_range,'partial_sha256':hashlib.sha256(payload).hexdigest(),
            'parsed_rows':len(rows),'first_onset_seconds':onsets[0],'last_onset_seconds':onsets[-1],
            'first_onset_step_seconds':onsets[1]-onsets[0],
            'all_parsed_durations_zero':all(float(row['duration'])==0 for row in rows)}


def main():
    if OUTPUT.exists():
        raise RuntimeError('Existing metadata audit preserved')
    tree = json.loads(fetch(f'https://api.github.com/repos/OpenNeuroDatasets/ds008446/git/trees/{COMMIT}?recursive=1'))
    paths = [row['path'] for row in tree['tree'] if row['path'].endswith('_channels.tsv')]
    with ThreadPoolExecutor(max_workers=8) as pool:
        channels = list(pool.map(inspect_channels,sorted(paths)))
    description = json.loads(fetch(RAW+'dataset_description.json'))
    example_json = 'sub-01/eeg/sub-01_task-random_run-01_eeg.json'
    eeg = json.loads(fetch(RAW+example_json))
    head,tail = event_range(),event_range(tail=True)
    report = {'dataset':'ds008446','doi':description['DatasetDOI'],'license':description['License'],
              'pinned_github_commit':COMMIT,'fixed_montage':FIXED,'checked_channel_sidecars':len(channels),
              'all_checked_runs_have_fixed8':all(not row['missing_fixed_channels'] for row in channels),
              'channels':channels,'example_eeg_metadata':eeg,'example_eeg_json_path':example_json,
              'events_head':head,'events_tail':tail,
              'timing_warning':{'recording_duration_seconds':eeg['RecordingDuration'],
                                'sampling_frequency_hz':eeg['SamplingFrequency'],
                                'event_step_matches_one_sample':abs(head['first_onset_step_seconds']-1/eeg['SamplingFrequency'])<1e-8,
                                'event_range_within_first_recording_second_fraction':tail['last_onset_seconds']/eeg['RecordingDuration'],
                                'action':'Do not train from these timestamps as-is; verify native EDF Marker and cue transitions before trial construction; no automatic rescaling'},
              'label_map_from_author_readme':{'3':'thumb','4':'index','5':'middle','6':'ring','7':'little'},
              'candidate_training_ready':False,'finger_accuracy_measured':False,'eeg_downloaded':False,
              'only_metadata_and_two_4096byte_event_ranges_read':True,'board_accessed':False,
              'control_enabled':False,'completed_at_local':datetime.now().isoformat()}
    OUTPUT.mkdir()
    (OUTPUT/'metadata_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('dataset','license','checked_channel_sidecars','all_checked_runs_have_fixed8','timing_warning','candidate_training_ready')},indent=2))


if __name__=='__main__':main()
