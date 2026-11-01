"""Descriptive source-only join diagnostic; does not select or fit a model."""
from pathlib import Path
from datetime import datetime

from mi_comparison_models import torch, channel_scaler, normalized_tensor
from mi_segmentation import SourceSegments
from mi_segmentation_experiment import load_experiment, OUTPUT
from mi_model_comparison import fold_indices
from cho2017_data import hashes
from cho2017_training_diagnostic import save
import numpy as np
from scipy.signal import welch


def main():
    destination = OUTPUT/'join_diagnostic.json'
    if destination.exists():raise RuntimeError('Existing diagnostic preserved')
    _, _, stats, waves, folds = load_experiment(OUTPUT)
    fitting, _, _ = fold_indices(stats['subjects'],stats['order'],folds[0])
    mean, scale = channel_scaler(waves[fitting])
    values = normalized_tensor(waves[fitting],mean,scale,'cpu')
    builder = SourceSegments(stats['labels'][fitting],stats['subjects'][fitting],'cpu',42)
    anchors = torch.arange(min(len(values),1000))
    synthetic, _ = builder.reconstruct(values,anchors)
    original = values[anchors].numpy()[:,0]; synthetic = synthetic.numpy()[:,0]
    boundaries = np.array(builder.boundaries[1:-1])
    freq, original_psd = welch(original,fs=250,nperseg=250,axis=-1)
    _, synthetic_psd = welch(synthetic,fs=250,nperseg=250,axis=-1)
    conditions = {}
    for name, values, psd in [('original',original,original_psd),('synthetic',synthetic,synthetic_psd)]:
        jumps = np.abs(values[:,:,boundaries]-values[:,:,boundaries-1])
        ratio = psd[:,:,(freq>=40)&(freq<=100)].sum(-1)/psd[:,:,(freq>=8)&(freq<=30)].sum(-1)
        conditions[name] = {'join_abs_difference_in_source_channel_std_units_median_p95':np.quantile(jumps,[.5,.95]).tolist(),
                            'welch_40_100Hz_power_to_8_30Hz_power_median_p95':np.quantile(ratio,[.5,.95]).tolist()}
    report = {'scope':'Descriptive only;first1000 fitting rows of the first predeclared fold,not target data or performance-based selection',
              'fold':folds[0],'fitting_anchors':len(anchors),'anchor_people':sorted(np.unique(stats['subjects'][fitting[:len(anchors)]]).tolist()),
              'augmentation_seed':42,'boundaries':builder.boundaries,'conditions':conditions,
              'interpretation':'Joining independent same-person same-class segments increases jumps and out-of-band energy in this diagnostic. This does not establish a causal explanation for any accuracy change; a new ablation would be needed.',
              'training_or_protocol_changed':False,'model_fitted':False,'confirmation_eeg_read':False,
              'board_accessed':False,'control_enabled':False,'script_sha256':hashes(Path(__file__))['sha256'],
              'completed_at_local':datetime.now().isoformat()}
    save(destination,report)
    print(conditions)


if __name__=='__main__':main()
