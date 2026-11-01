"""Preserve the original/audio; prepare a silent contained portrait-canvas cache."""
import argparse
import json
from pathlib import Path
import subprocess
from upload_server import write_json,file_sha
from prepare_display_asset import prepare


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    base=Path(__file__).resolve().parent
    args.output.mkdir(mode=0o700,exist_ok=False)
    original_sha=file_sha(args.source)
    audio=subprocess.run([str(base/'audio_probe'),str(args.source)],capture_output=True,
                         text=True,check=True,timeout=65)
    write_json(args.output/'audio.json',json.loads(audio.stdout))
    prepare(args.source,args.output/'cache')
    if file_sha(args.source)!=original_sha:raise ValueError('Original changed')
    write_json(args.output/'ready.json',{'original_preserved':True,'source_sha256':original_sha,
        'silent':True,'audio_output':False,'audio_sidecar':'audio.json','cache':'cache'})


if __name__=='__main__':main()
