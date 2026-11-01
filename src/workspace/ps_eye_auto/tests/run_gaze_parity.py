"""Execute actual firmware main.c with host hardware mocks, compare PC adapter."""
import subprocess
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def run():
    harness=(ROOT/'tests/test_gaze_parity.c').read_text(encoding='utf-8')
    firmware=(ROOT/'src/app/main.c').read_text(encoding='utf-8')
    firmware='\n'.join(line for line in firmware.splitlines() if not line.startswith('#include'))
    harness=harness.replace('/* FIRMWARE_MAIN */',firmware)
    # Resolve this include against the authored file, not the temporary directory.
    harness=harness.replace('"../tools/pc_gaze_bridge.c"','"'+(ROOT/'tools/pc_gaze_bridge.c').as_posix()+'"')
    with tempfile.TemporaryDirectory(prefix='z15_gaze_parity_') as temp:
        src=Path(temp)/'parity.c';exe=Path(temp)/'parity.exe'
        src.write_text(harness,encoding='utf-8')
        subprocess.run(['C:/mingw64/mingw64/bin/gcc.exe','-std=c11','-O2','-Wall','-Wextra','-Werror',
                        '-Itests/include','-Isrc/app',str(src),'src/app/eye_tracker.c',
                        'src/app/auto_face.c','src/app/haar.c','-lm','-o',str(exe)],cwd=ROOT,check=True)
        subprocess.run([str(exe)],check=True)
if __name__=='__main__':run()
