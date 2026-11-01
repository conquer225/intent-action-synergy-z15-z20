"""Preserve the previous full archive and append the paired EEG update."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--previous',type=Path,default=REPO/'delivery/GuardianLoop_Eye_C3_20261018.zip')
    parser.add_argument('--output',type=Path,default=REPO/'delivery/GuardianLoop_EEG_Demo_20261018.zip');args=parser.parse_args()
    rows=[]
    for source in sorted(ROOT.rglob('*')):
        rel=source.relative_to(ROOT)
        if not source.is_file() or any(p in ('__pycache__','.eeg-demo-backups') for p in rel.parts):continue
        if source.suffix in ('.pyc','.dll','.so') or source.name in ('test-recording.json','PAYLOAD_SHA256.txt'):continue
        rows.append((source,rel.as_posix(),hashlib.sha256(source.read_bytes()).hexdigest()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.previous) as old,zipfile.ZipFile(args.output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as new:
        root=old.namelist()[0].split('/')[0]
        for info in old.infolist():new.writestr(info,old.read(info))
        prefix=root+'/eeg_demo_update/'
        for source,name,sha in rows:new.write(source,prefix+name)
        listing=''.join(sha+'  '+name+'\n' for _,name,sha in rows)
        new.writestr(prefix+'PAYLOAD_SHA256.txt',listing)
    with zipfile.ZipFile(args.previous) as old,zipfile.ZipFile(args.output) as new:
        if new.testzip():raise ValueError('ZIP CRC mismatch')
        for info in old.infolist():
            if hashlib.sha256(old.read(info)).digest()!=hashlib.sha256(new.read(info.filename)).digest():raise ValueError(info.filename)
        for _,name,sha in rows:
            if hashlib.sha256(new.read(prefix+name)).hexdigest()!=sha:raise ValueError(name)
        result=dict(previous_files_preserved=len(old.infolist()),update_files=len(rows),zip_entries=len(new.infolist()),crc_verified=True,source_hashes_verified=True)
    checksum=hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix('.zip.sha256').write_text(checksum+'  '+args.output.name+'\n',encoding='ascii')
    result.update(path=str(args.output),sha256=checksum,bytes=args.output.stat().st_size)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
