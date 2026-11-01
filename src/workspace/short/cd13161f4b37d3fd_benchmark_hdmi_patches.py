"""Normal-RAM corner-copy cost only; no PYNQ, DMA, MMIO or screen output."""
import argparse
import json
from pathlib import Path
import time

import numpy as np

from hdmi_stimulus import StimulusFrames
from ssvep_hdmi import SCAN_PERIOD, pattern
from system_hdmi import UnifiedDisplay


class RamBuffer(np.ndarray):
    def flush(self):pass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--eye-root',type=Path,required=True)
    args=parser.parse_args()
    display=UnifiedDisplay(args.eye_root,live=True,dimensions=(288,512))
    frames=StimulusFrames(display)
    buffers=[np.empty((720,1280,3),dtype=np.uint8).view(RamBuffer) for _ in range(3)]
    for i,buffer in enumerate(buffers):frames.paint(buffer,i,pattern(0))
    times=[]
    for n in range(1000):
        i=n%3;start=time.perf_counter()
        frames.paint(buffers[i],i,pattern(n),12 if 500<=n<700 else None)
        times.append((time.perf_counter()-start)*1000)
    print(json.dumps(dict(scope='normal_ram_copy_only_no_cache_flush_or_dma',scans=1000,
        patch_memory_mib=sum(x.nbytes for x in frames.patches.values())/1024**2,
        scan_budget_ms=SCAN_PERIOD*1000,median_ms=float(np.median(times)),
        p95_ms=float(np.percentile(times,95)),maximum_ms=max(times),
        over_scan_budget=sum(t>SCAN_PERIOD*1000 for t in times),
        visible_stimulus_tested=False,physical_output_enabled=False)))


if __name__=='__main__':main()
