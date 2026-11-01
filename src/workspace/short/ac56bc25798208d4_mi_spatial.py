"""NumPy-only spatial MI math; no acquisition, training labels or control output."""
import numpy as np

from mi_features import CHANNELS, WINDOW_SAMPLES


def normalized_covariance(window, expected_samples=WINDOW_SAMPLES):
    values=np.asarray(window,dtype=np.float64)
    if (not isinstance(expected_samples,(int,np.integer)) or expected_samples<2
            or values.shape!=(expected_samples,len(CHANNELS)) or not np.isfinite(values).all()):
        raise ValueError('Expected finite declared-window-by-eight band-filtered samples')
    centered=values-values.mean(axis=0)
    cov=centered.T@centered/(len(values)-1)
    trace=float(np.trace(cov))
    if trace<=1e-12:
        raise ValueError('Flat or degenerate MI window')
    return cov/trace


def projected_features(covariances, filters):
    cov=np.asarray(covariances,dtype=np.float64)
    spatial=np.asarray(filters,dtype=np.float64)
    if (cov.ndim!=4 or cov.shape[2:]!=(8,8) or spatial.ndim!=3
            or spatial.shape[0]!=cov.shape[1] or spatial.shape[2]!=8
            or not np.isfinite(cov).all() or not np.isfinite(spatial).all()):
        raise ValueError('Expected trials-by-bands-by-eight covariance and fixed spatial filters')
    power=np.einsum('bki,nbij,bkj->nbk',spatial,cov,spatial)
    return np.log(np.maximum(power,1e-12)).reshape(len(cov),-1)


def linear_scores(covariances,filters,mean,scale,coef,intercept):
    features=projected_features(covariances,filters)
    mean,scale,coef=(np.asarray(value,dtype=np.float64) for value in (mean,scale,coef))
    if (mean.shape!=features.shape[1:] or scale.shape!=mean.shape or coef.shape!=mean.shape
            or not np.isfinite([*mean,*scale,*coef,float(intercept)]).all() or np.any(scale<=0)):
        raise ValueError('Invalid spatial linear model')
    return ((features-mean)/scale)@coef+float(intercept)
