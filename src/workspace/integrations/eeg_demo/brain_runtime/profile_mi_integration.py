"""Short recorded-only diagnostic, not a timing acceptance run."""
import cProfile
import json
from pathlib import Path
import sys
import threading
import time

import mi_acquisition
import mi_multitask_replay


def main():
    out=Path(sys.argv[sys.argv.index('--output')+1]).resolve()
    measurements={}
    guard=threading.Lock()

    def timed(owner,name,label):
        original=getattr(owner,name)
        def invoke(self,*args,**kwargs):
            started=time.thread_time()
            try:
                return original(self,*args,**kwargs)
            finally:
                elapsed=time.thread_time()-started
                with guard:
                    entry=measurements.setdefault(label,dict(calls=0,thread_cpu_seconds=0))
                    entry['calls']+=1
                    entry['thread_cpu_seconds']+=elapsed
        setattr(owner,name,invoke)

    timed(mi_acquisition.MIAcquisition,'packet','mi_packet')
    timed(mi_acquisition.CuedMISession,'feed','mi_batch')
    timed(mi_acquisition.CuedMISession,'disconnect','mi_reset')
    profile=cProfile.Profile()
    profile.enable()
    try:
        mi_multitask_replay.main()
    finally:
        profile.disable()
        if out.is_dir():
            profile.dump_stats(str(out/'main-thread.prof'))
            (out/'mi-cpu-diagnostic.json').write_text(json.dumps(dict(
                diagnostic_only=True,not_for_acceptance=True,measurements=measurements,
                scope='Main thread cProfile; MI thread CPU counters. CPU counters may overlap for nested calls.')))


if __name__=='__main__':
    main()
