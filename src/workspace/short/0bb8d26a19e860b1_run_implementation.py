"""Build the authorised isolated audio overlay. Does not contact Z15 or program hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from rebuild_display import HWH, VENDOR, REFERENCE_PINS, REFERENCE_HDMI
from run_simulation import HERE, BIN, SERIALIZER


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-directory',type=Path,required=True)
    args=parser.parse_args()
    out=args.project_directory.resolve()
    if out.parent != (HERE/'output').resolve() or not (out/'project/hdmi_audio.xpr').is_file():
        raise ValueError('Not an isolated audio candidate project')
    for suite in ['pcm','pcm_ticks','pcm_capacity','packets','video','serial','status']:
        records=sorted((HERE/'output').glob('*_sim_*/result.json'),key=lambda p:p.stat().st_mtime)
        results=[json.loads(p.read_text()) for p in records if json.loads(p.read_text())['scope'].startswith(suite+' ')]
        if not results or not results[-1]['passed']:
            raise RuntimeError('Missing passing '+suite+' simulation')
        for name,digest in results[-1]['sources'].items():
            if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:
                raise RuntimeError('Stale simulation: '+name)
    sources=[HWH,SERIALIZER,REFERENCE_PINS,REFERENCE_HDMI,
             *sorted((HERE/'rtl').glob('*.sv')),*sorted((HERE/'third_party/hdmi/src').glob('*.sv')),
             *sorted((VENDOR/'ov5640_cap_data').rglob('*.v')),
             HERE/'create_display.tcl',HERE/'implement_display.tcl',HERE/'rebuild_display.py',
             out/'legacy_contract.tcl',out/'pins.xdc']
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    with (out/'implementation-inputs.json').open('x') as f:
        json.dump(dict(part='xc7z015clg485-2',sources=hashes,board_loading_authorized=False),f,indent=2)
    command=[str(BIN/'vivado.bat'),'-mode','batch','-nojournal','-log',(out/'implement.log').as_posix(),
             '-source',(HERE/'implement_display.tcl').as_posix(),'-tclargs',out.as_posix()]
    result=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=3600)
    print('\n'.join((result.stdout+result.stderr).splitlines()[-90:]),flush=True)
    if result.returncode or 'DISPLAY_AUDIO_CANDIDATE_BUILT_NOT_LOADED' not in result.stdout:
        raise RuntimeError('Full build stopped; inspect '+str(out/'implement.log'))
    if hashes!={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}:
        raise RuntimeError('Sources changed during build; do not load this artifact')
    artifacts={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'candidate').iterdir() if p.is_file()}
    (out/'result.json').write_text(json.dumps(dict(passed=True,scope='candidate bit/hwh only; not loaded, no audible validation',
        artifacts=artifacts,sources=hashes),indent=2))


if __name__=='__main__':
    main()
