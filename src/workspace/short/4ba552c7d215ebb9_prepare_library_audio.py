"""Prepare independent audio caches from the audited video playlist, never playback."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from level_audio import level, measure


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def prepare(playlist, output, preparer):
    output=Path(output);output.mkdir(mode=0o700,exist_ok=False)
    reports={}
    for row in playlist:
        ident=row['id']
        if not ident or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789' for c in ident):
            raise ValueError('Invalid local video identifier')
        source=Path(row['download'])
        if row['source']=='SD_card':
            source=source.with_name('portrait-source.avi')
        original=sha(source)
        raw=output/(ident+'-decoded.wav')
        result=subprocess.run([str(preparer),str(source),str(raw)],
                              capture_output=True,text=True,timeout=190)
        if result.returncode:
            raise RuntimeError('Audio preparation failed for '+ident+': '+result.stderr[-800:])
        report=json.loads(result.stdout)
        meta=json.loads((Path(row['cache'])/'manifest.json').read_text())
        report.update(source=str(source),source_sha256=original,video_seconds=meta['frames']/meta['fps'],
                      audio_played=False,PL_loaded=False)
        if report['audio_present']:
            if abs(report['first_pts_seconds'])>1/48000:
                report.update(ready=False,reason='nonzero_audio_start_requires_alignment')
            elif not measure(raw)['peak']:
                report.update(ready=False,reason='track_contains_digital_silence')
            else:
                normalized=output/(ident+'.wav')
                report['level']=level(raw,normalized)
                report.update(ready=True,path=str(normalized),sha256=sha(normalized),
                              av_duration_difference_s=report['duration_seconds']-report['video_seconds'])
        else:
            report.update(ready=False,reason='source_has_no_audio_track')
            if raw.exists():
                raise RuntimeError('No-audio result unexpectedly published a PCM file')
        if sha(source)!=original:
            raise RuntimeError('Original video changed during preparation')
        reports[ident]=report
        (output/'library-audio.json').write_text(json.dumps(reports,indent=2))
    return reports


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--playlist',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--preparer',type=Path,required=True)
    args=parser.parse_args()
    playlist=json.loads(args.playlist.read_text())['playlist']
    print(json.dumps(prepare(playlist,args.output,args.preparer)))
