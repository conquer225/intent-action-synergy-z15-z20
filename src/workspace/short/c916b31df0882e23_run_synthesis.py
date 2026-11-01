"""Synthesize isolated components; never loads a board or generates a complete overlay."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from run_simulation import BIN, HERE, SERIALIZER


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise FileExistsError(out)
    sources = [*sorted((HERE/'rtl').glob('*.sv')), *sorted((HERE/'third_party/hdmi/src').glob('*.sv')),
               SERIALIZER, HERE/'synth_components.tcl']
    hashes = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    for suite in ['pcm', 'packets', 'video', 'serial']:
        results = sorted((HERE/'output').glob('*_sim_*/result.json'), key=lambda p:p.stat().st_mtime)
        matching = [json.loads(p.read_text()) for p in results if json.loads(p.read_text())['scope'].startswith(suite+' ')]
        if not matching or not matching[-1]['passed']:
            raise RuntimeError('Missing passing '+suite+' simulation')
        for name, digest in matching[-1]['sources'].items():
            if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
                raise RuntimeError('Simulation is stale: '+name)
    log_path = out.with_suffix('.log')
    journal_path = out.with_suffix('.jou')
    if log_path.exists() or journal_path.exists():
        raise FileExistsError('Existing synthesis logs: '+str(out))
    command = [str(BIN/'vivado.bat'), '-mode', 'batch', '-nojournal', '-log', str(log_path),
               '-source', str(HERE/'synth_components.tcl'), '-tclargs', str(HERE), str(out), str(SERIALIZER)]
    result = subprocess.run(command, cwd=HERE, capture_output=True, text=True, timeout=900)
    print('\n'.join(result.stdout.splitlines()[-80:]), flush=True)
    if result.returncode or 'AUDIO_COMPONENT_SYNTH_PASS' not in result.stdout:
        raise RuntimeError('Synthesis failed; see '+str(log_path))
    if hashes != {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}:
        raise RuntimeError('Sources changed during synthesis')
    (out/'result.json').write_text(json.dumps(dict(passed=True, part='xc7z015clg485-2',
        scope='out-of-context component synthesis only; no implementation, bitstream, board loading or audio playback',
        sources=hashes), indent=2))


if __name__ == '__main__':
    main()
