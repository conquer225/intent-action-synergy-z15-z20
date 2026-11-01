"""Paired CPU/wall microbenchmark against an archived, unmodified implementation."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

import numpy as np
from ssvep_core import CachedCCA, reference_bank
from cyton_sqi import channel_sqi


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    old=load('reference_cca',args.baseline/'ssvep_core.py')
    old_sqi=load('reference_sqi',args.baseline/'cyton_sqi.py')
    refs=reference_bank((8,10,12,14),samples=500)
    cached=CachedCCA(refs)
    timing=[]
    maximum=0.
    for seed in (0,11,42):
        rng=np.random.default_rng(seed)
        windows=[rng.normal(size=(2,500))*scale+offset for scale,offset in
                 ((1,0),(30,0),(100,10000),(1e-5,0))]*25
        for x in windows[:4]:
            a=np.array([old.canonical_correlation(x,r) for r in refs])
            b=cached.scores(x)
            np.testing.assert_allclose(a,b,atol=1e-9,rtol=1e-7)
            maximum=max(maximum,float(np.max(np.abs(a-b))))
        data=rng.normal(size=(500,8))*30
        np.testing.assert_array_equal(channel_sqi(data),old_sqi.channel_sqi(data))
        np.testing.assert_array_equal(channel_sqi(data,channel_indices=(0,1,2,3)),old_sqi.channel_sqi(data)[:4])
        jobs={
            'cca_original':lambda:[old.canonical_correlation(x,r) for x in windows for r in refs],
            'cca_cached':lambda:[cached.scores(x) for x in windows],
            'sqi_original':lambda:[old_sqi.channel_sqi(data) for _ in range(100)],
            'sqi_cached_subset':lambda:[channel_sqi(data,channel_indices=(0,1,2,3)) for _ in range(100)]}
        names=list(jobs)
        if seed==11: names.reverse()
        for name in names:
            start=time.perf_counter(); cpu=time.process_time()
            jobs[name]()
            timing.append(dict(seed=seed,name=name,windows=100,
                wall_seconds=time.perf_counter()-start,cpu_seconds=time.process_time()-cpu))
    report=dict(passed=True,maximum_score_error=maximum,sqi_exact=True,runs=timing,
                scope='100 windows per kernel x3 deterministic seeds; initialization excluded; no USB or PL')
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
