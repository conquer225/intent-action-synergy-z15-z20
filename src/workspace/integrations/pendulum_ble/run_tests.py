"""Run public BLE-session behavior checks with a C++17 compiler."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cxx', default=shutil.which('g++') or shutil.which('clang++') or shutil.which('cl'))
    args = p.parse_args()
    if not args.cxx:
        p.error('Supply --cxx, or run from a compiler developer shell.')
    root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='guardianloop-ble-') as tmp:
        include = root / 'firmware' / 'MultiControlS3'
        for name in ('test_ble_session','test_radio_resync','test_network_latency','test_hand_preparation'):
            out=Path(tmp)/(name+'.exe');source=root/'tests'/(name+'.cpp')
            includes=[include]
            if name in ('test_radio_resync','test_hand_preparation'):
                includes.insert(0,root/'tests/radiostubs')
            if Path(args.cxx).name.lower() in ('cl','cl.exe'):
                command=[args.cxx,'/nologo','/std:c++17','/EHsc','/W4','/wd4505',
                         *['/I'+str(p) for p in includes],str(source),'/Fe:'+str(out),'/Fo:'+str(Path(tmp)/(name+'.obj'))]
            else:
                command=[args.cxx,'-std=c++17','-Wall','-Wextra',*['-I'+str(p) for p in includes],str(source),'-o',str(out)]
                if os.name=='nt':command+=['-static']
                if name=='test_network_latency' and os.name=='nt':
                    command+=['-lws2_32']
            subprocess.run(command,check=True,cwd=tmp)
            subprocess.run([str(out)],check=True)



if __name__ == '__main__':
    main()
