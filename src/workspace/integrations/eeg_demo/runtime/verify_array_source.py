"""Compare the explicitly staged ring with the untouched release stream."""
import json
import numpy as np
from cyton_covariance import CovarianceFeatureStream as Original
from covariance_array_source import CovarianceFeatureStream as Candidate

channels=('F3','F4','C3','C4','T7','T8','O1','O2')
original=Original(channels);candidate=Candidate(channels,storage='array')
rng=np.random.default_rng(61);data=rng.normal(size=(7500,8));offset=0;compared=0;maximum=0.
for count in (10,500,600,2000,10,1000,3000,380):
    block=data[offset:offset+count];offset+=count
    original.append(block);candidate.append(block)
    if original.ready!=candidate.ready:raise ValueError('Readiness changed')
    if original.ready:
        left,right=original.feature(),candidate.feature()
        maximum=max(maximum,float(np.max(np.abs(left-right))))
        if not np.array_equal(left,right):raise ValueError('Ring feature values changed')
        compared+=1
if offset!=len(data) or not compared:raise ValueError('Incomplete fixture')
print(json.dumps(dict(compared_windows=compared,maximum_feature_error=maximum,exact=True)))
