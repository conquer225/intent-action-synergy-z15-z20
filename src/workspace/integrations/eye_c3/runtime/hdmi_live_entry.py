"""Temporary SSVEP module substitution around the unchanged formal ARM entry."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import sys

MODULES = ('ssvep_free', 'ssvep_hdmi', 'ssvep_cue_runtime')
FORMAL = Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')


def load_modules(directory, hashes):
    directory = Path(directory)
    if set(hashes) != set(MODULES):
        raise ValueError('Only the three audited SSVEP modules may be substituted')
    for name in MODULES:
        path = directory / (name + '.py')
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashes[name]:
            raise ValueError('Candidate module changed: ' + name)
    for name in MODULES:
        path = directory / (name + '.py')
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules['ssvep_cue_runtime']


def prepare(state_path):
    path = Path(state_path).resolve()
    if path.parent != Path(__file__).resolve().parent:
        raise ValueError('State must belong to this isolated entry')
    state = json.loads(path.read_text())
    if state['formal_entry'] != str(FORMAL / 'guardianloop_acquisition.py'):
        raise ValueError('Formal acquisition entry changed')
    for name, expected in state['formal_hashes'].items():
        if Path(name).name != name:
            raise ValueError('Invalid formal artifact name')
        if hashlib.sha256((FORMAL / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Formal artifact changed: ' + name)
    sys.path.insert(0, str(FORMAL))
    cue = load_modules(state['candidate_runtime'], state['module_hashes'])
    cue.LOG_PATH = path.parent / 'ssvep_cued_trials.jsonl'
    return state, cue


def acquisition_worker(*args):
    # Spawn may import the decoder before invoking this function. Replace the
    # constructor explicitly; the original worker and packet tap stay unchanged.
    _, cue = prepare(os.environ['GL_HDMI_LIVE_STATE'])
    # The audited native scanner uses CPU1; keep its live producer on CPU0.
    os.sched_setaffinity(0, {0})
    os.setpriority(os.PRIO_PROCESS, 0, -5)
    import ssvep_acquisition
    ssvep_acquisition.SSVEPCueRuntime = cue.SSVEPCueRuntime
    ssvep_acquisition._worker(*args)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--formal-entry', required=True)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    state, _ = prepare(args.state)
    if args.formal_entry != state['formal_entry']:
        raise ValueError('Entry argument differs from verified state')
    os.environ['GL_HDMI_LIVE_STATE'] = str(args.state.resolve())
    import ssvep_acquisition
    import hdmi_live_entry as worker_entry
    ssvep_acquisition._worker = worker_entry.acquisition_worker
    if args.preflight:
        from cyton_guardianloop import decode_eeg_counts
        from urllib.request import urlopen
        worker = ssvep_acquisition.SSVEPReaderRuntime(
            FORMAL / 'ssvep_causal_protocol.json', FORMAL / 'ssvep_candidate_sos.npy',
            ('F3','F4','C3','C4','T7','T8','O1','O2'), decode_eeg_counts,
            4.5 / (24 * (2**23-1)) * 1_000_000,
            status_path=args.state.parent / 'preflight_ssvep.json',
            log_path=args.state.parent / 'preflight_events.jsonl', port=0)
        try:
            with urlopen('http://127.0.0.1:%s/api/ssvep-hdmi' % worker.port, timeout=3) as response:
                result = json.load(response)
            if (result.get('policy') != 'ssvep-hdmi-experimental-v1'
                    or result.get('control_enabled') is not False):
                raise ValueError('Spawned HDMI backend identity mismatch')
            print('SPAWN_PREFLIGHT_PASSED_NO_SERIAL_NO_PL', flush=True)
        finally:
            worker.close()
        return
    arguments = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
    sys.argv = [args.formal_entry, *arguments]
    print('HDMI_TEMPORARY_BACKEND: formal ARM entry, packet tap, models and gates retained', flush=True)
    runpy.run_path(args.formal_entry, run_name='__main__')


if __name__ == '__main__':
    main()
