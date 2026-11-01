"""Create a self-contained source/release archive; exclude working build caches."""
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TREES=('intent_one','hardware','vendor','firmware','board_runtime','config','tools','tests','skills','report','release')
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT.parent/'delivery/intent_one_20261014.zip');a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    files=[]
    for tree in TREES:
        for f in (ROOT/tree).rglob('*'):
            if not f.is_file() or '__pycache__' in f.parts or f.name=='WifiConfig.h':continue
            if tree=='firmware' and (any(x in ('build','Objects','Listings') for x in f.relative_to(ROOT/'firmware').parts) or f.suffix.lower() in ('.obj','.exe','.pdb','.ilk')):continue
            files.append(f)
    files+=list(ROOT.glob('*.md'))+[ROOT/'baseline_manifest.json']
    with zipfile.ZipFile(a.output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for file in sorted(set(files)):archive.write(file,'intent_one/'+file.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(a.output) as archive:
        error=archive.testzip()
        if error:raise RuntimeError('CRC mismatch: '+error)
    value={'archive':a.output.name,'sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'files':len(set(files)),'bytes':a.output.stat().st_size}
    a.output.with_suffix('.json').write_text(json.dumps(value,indent=2),encoding='utf8');print(json.dumps(value))
if __name__=='__main__':main()
