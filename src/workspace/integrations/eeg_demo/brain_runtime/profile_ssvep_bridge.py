"""Bounded hotspot diagnostic, with only sandbox replay status writes."""
import cProfile
from pathlib import Path
import pstats

import numpy as np

from ssvep_shadow import CHANNELS, SSVEPShadow


def run():
    root = Path(__file__).resolve().parent
    data = np.loadtxt(root.parent/'recorded.txt', delimiter=',', skiprows=5, usecols=range(9), max_rows=3000)
    shadow = SSVEPShadow(root/'ssvep_causal_protocol.json', root/'ssvep_candidate_sos.npy',
                        CHANNELS, source='replay', status_path=root/'hotspot_status.json')
    profile = cProfile.Profile()
    profile.enable()
    for i,row in enumerate(data):
        shadow.packet(row[1:9], int(row[0]), now=i/250)
    profile.disable()
    profile.dump_stats(str(root/'bridge_hotspots.prof'))
    pstats.Stats(profile).strip_dirs().sort_stats('cumtime').print_stats(25)


if __name__=='__main__':
    run()
