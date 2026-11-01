"""Persist software test evidence without touching hardware or importing PYNQ."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tkinter
import unittest

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    if out.exists():
        raise FileExistsError(out)
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(HERE), pattern='test_*.py')
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    log = stream.getvalue()
    print(log)
    # Sourcing defines a procedure only. This checks Tcl parsing, NOT Vivado API validity.
    interpreter = tkinter.Tcl()
    interpreter.call('source', str(HERE/'attach_candidate.tcl'))
    defined = bool(interpreter.call('info', 'procs', 'primary_filter_candidate::attach'))
    files = [HERE/name for name in ('primary_filter_dma.py','test_primary_filter_dma.py',
                                   'fixed_sos.py','test_fixed_sos.py','attach_candidate.tcl','audit_adapter.py')]
    evidence = dict(passed=result.wasSuccessful() and defined, tests=result.testsRun,
                    failure_count=len(result.failures), error_count=len(result.errors),
                    tcl_definition_parsed=defined, vivado_bd_validated=False,
                    physical_dma_tested=False, production_changed=False,
                    scope='Software register model and Tcl definition parsing only',
                    log=log, sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    if not evidence['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
