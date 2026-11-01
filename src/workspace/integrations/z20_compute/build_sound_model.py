"""Public recorded clap/whistle/knock assets, grouped by original recording."""
import csv
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import urllib.request
import wave
import zipfile
import numpy as np

sys.path.insert(0, str(Path('build/pc_audio_deps').resolve()))
import soundfile
from z20_compute.audio import resample_audio, sound_features
from z20_compute.training import Dataset, train_mlp

ROOT = Path('artifacts/headless/sound')
BASE = 'https://raw.githubusercontent.com/karolpiczak/ESC-50/master/'


def download(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read(10*1024*1024+1)
        if len(data) > 10*1024*1024: raise ValueError('sound source exceeds bound')
        path.write_bytes(data)
    return path.read_bytes()


def main():
    metadata = {}
    with zipfile.ZipFile('build/headless-sound/FSD50K.metadata.zip') as archive:
        for split in ('dev', 'eval'):
            metadata.update(json.load(archive.open('FSD50K.metadata/'+split+'_clips_info_FSD50K.json')))
    csv_data = download(BASE+'meta/esc50.csv', ROOT/'sources/esc50.csv').decode()
    sources = []
    for row in csv.DictReader(io.StringIO(csv_data)):
        if row['category'] not in ('clapping', 'door_wood_knock'): continue
        info = metadata.get(row['src_file'])
        if info is None or not any(token in info['license'] for token in ('/zero/', '/by/')): continue
        sources.append(dict(label=0 if row['category']=='clapping' else 2,
            filename=row['filename'], url=BASE+'audio/'+row['filename'],
            page='https://freesound.org/people/'+info['uploader']+'/sounds/'+row['src_file']+'/',
            author=info['uploader'], title=info['title'], license=info['license'],
            dataset_license='ESC-50 CC-BY-NC; original clip license also retained',
            group='freesound:'+row['src_file'],
            split='train' if int(row['fold'])<=3 else 'validation' if row['fold']=='4' else 'test'))
    # Descriptions explicitly identify human mouth whistling; no birds, kettles,
    # synthetic tones or AI-generated sounds are substituted for this class.
    for author, sound_id, split in [
        ('kayasavas87', '70772', 'train'), ('georgisound', '369296', 'train'),
        ('MonteFlorSounds', '847608', 'train'), ('chaosportal', '137106', 'train'),
        ('jperezjacome', '411506', 'validation'), ('Reitanna', '242627', 'test'),
        ('HOrvi64', '832320', 'test'), ('ldman165', '835856', 'test')]:
        page='https://freesound.org/people/'+author+'/sounds/'+sound_id+'/'
        html=download(page, ROOT/'sources'/('freesound-'+sound_id+'.html')).decode()
        if 'creativecommons.org/publicdomain/zero/1.0' not in html:
            raise ValueError('expected explicit CC0 license: '+page)
        urls=re.findall(r'https://cdn\.freesound\.org/previews/[0-9]+/[0-9_]+-hq\.mp3',html)
        if not urls: raise ValueError('public preview missing: '+page)
        sources.append(dict(label=1, filename='whistle-'+sound_id+'.mp3', url=urls[0],
            page=page, author=author, title='Human whistling '+sound_id,
            license='https://creativecommons.org/publicdomain/zero/1.0/',
            group='whistle-author:'+author, split=split,
            representation='Freesound public high-quality MP3 preview'))
    def fetch(row):
        data=download(row['url'],ROOT/'sources'/row['filename'])
        row['sha256']=hashlib.sha256(data).hexdigest()
        return row
    with ThreadPoolExecutor(max_workers=4) as pool: sources=list(pool.map(fetch,sources))
    xs, ys, groups, splits, windows = [], [], [], [], []
    for row in sources:
        samples, rate = soundfile.read(ROOT/'sources'/row['filename'], dtype='float64', always_2d=True)
        samples = resample_audio(samples.mean(axis=1), int(rate))
        if len(samples)<16000: samples=np.pad(samples,(0,16000-len(samples)))
        peak=float(np.max(np.abs(samples)))
        if peak>1: samples=samples/peak
        starts=list(range(0,len(samples)-16000+1,8000))
        energy=np.array([np.sqrt(np.mean(samples[start:start+16000]**2)) for start in starts])
        for index,start in enumerate(starts):
            if energy[index] < max(1e-4,.25*energy.max()): continue
            pcm=np.clip(np.rint(samples[start:start+16000]*32767),-32768,32767).astype('<i2')
            normalized=pcm.astype(np.float64)/32768.
            try: values=sound_features(normalized)
            except ValueError: continue
            name='clip-%04d.wav'%len(windows)
            (ROOT/'pcm').mkdir(parents=True,exist_ok=True)
            with wave.open(str(ROOT/'pcm'/name),'wb') as out:
                out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(pcm.tobytes())
            xs.append(values);ys.append(row['label']);groups.append(row['group']);splits.append(row['split'])
            windows.append(dict(file='pcm/'+name, source_filename=row['filename'], group=row['group'],
                split=row['split'], class_id=row['label'], start_seconds=start/16000.,
                labels_scope='source clip label inherited by active window',
                pcm_sha256=hashlib.sha256((ROOT/'pcm'/name).read_bytes()).hexdigest()))
    dataset=Dataset(np.array(xs),np.array(ys),np.array(groups),np.array(splits),
        source='ESC-50 clap/wood knock and documented human Freesound CC0 whistles; source-recording groups',
        source_kind='public')
    dataset.validate('sound');dataset.save(ROOT/'features.npz')
    model, report=train_mlp(dataset,'sound',epochs=500,group_balanced=True)
    model.save(Path('artifacts/headless/models/sound'))
    report['recordings']=len(sources);report['windows']=len(windows)
    report['split_groups']={split:len(set(dataset.groups[dataset.splits==split])) for split in ('train','validation','test')}
    (ROOT/'manifest.json').write_text(json.dumps(dict(sources=sources,windows=windows,
        scope='recorded files; clip-level labels, no live-microphone accuracy claim'),indent=2),encoding='utf-8')
    (ROOT/'training.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)


if __name__ == '__main__': main()
