"""Build the same localization C sources as a standalone Windows x64 DLL."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
INPUTS=['tools/pc_bridge.c','src/app/haar.c','src/app/haar.h','src/app/auto_face.c',
        'src/app/auto_face.h','src/app/eye_tracker.h','tests/include/xil_types.h',
        'src/app/face_model.inc','src/app/face_alt_model.inc','src/app/eye_model.inc']

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--gcc',default='C:/mingw64/mingw64/bin/gcc.exe')
    args=p.parse_args()
    out=ROOT/'pc_runtime';out.mkdir(exist_ok=True)
    dll=out/'model.dll'
    subprocess.run([args.gcc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-shared','-static-libgcc',
                    '-static','-Itests/include','-Isrc/app','src/app/haar.c','src/app/auto_face.c',
                    'tools/pc_bridge.c','-lm','-o',str(dll)],cwd=ROOT,check=True)
    hashes={name:hashlib.sha256((ROOT/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for name in INPUTS}
    manifest=dict(abi=1,dll_sha256=hashlib.sha256(dll.read_bytes()).hexdigest(),sources=hashes)
    (out/'model_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print('Built '+str(dll))
if __name__=='__main__':main()
