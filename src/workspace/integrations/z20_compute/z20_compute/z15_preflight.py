"""Read-only original-runtime version check; never updates network or control."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def check(legacy_directory,manifest):
    legacy_directory=Path(legacy_directory)
    expected=json.loads(Path(manifest).read_text(encoding='utf-8'))
    changed,missing=[],[]
    for name,digest in expected.items():
        if Path(name).name!=name:raise ValueError('manifest entries must be filenames')
        path=legacy_directory/name
        if not path.is_file():missing.append(name)
        elif hashlib.sha256(path.read_bytes()).hexdigest()!=digest:changed.append(name)
    return dict(passed=not missing and not changed and sys.version_info>=(3,7),
        python=sys.version,checked_files=len(expected),changed=changed,missing=missing,
        scope='file hashes and Python version; no Z15 installation or actuator test')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-dir',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,default=Path('original_hashes.json'))
    args=parser.parse_args();result=check(args.legacy_dir,args.manifest)
    print(json.dumps(result,indent=2));return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
