"""Verify the installed release and load the production PL once per boot."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from cyton_trial_recorder import atomic_json


STATUS_PATH = Path('/run/guardianloop-startup/status.json')
CHANNELS = ('F3', 'F4', 'C3', 'C4', 'T7', 'T8', 'O1', 'O2')
BIT_SHA256 = 'c39b891704471a712fb7be3591841af1dd6791387957b873b11450c99eca41ca'
HWH_SHA256 = '2ab7ffa36398be4eee20d90512c7f1c6d29a7066c9d1bf0683a3bcad2501f92b'
EXPECTED_IDS = {'de': 0x44453031, 'hgb': 0x48473031, 'model': 0x50537911}


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def verify_files(root, manifest):
    if tuple(manifest['channels']) != CHANNELS:
        raise ValueError('Release channel map does not match the fixed cap')
    files = manifest['files']
    if (files.get('guardianloop_pynq.bit') != BIT_SHA256 or
            files.get('guardianloop_pynq.hwh') != HWH_SHA256):
        raise ValueError('Release does not contain the production bit/HWH pair')
    for name, expected in files.items():
        if Path(name).name != name:
            raise ValueError('Release filenames must stay inside the application directory')
        actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('Release checksum mismatch: ' + name)
    configured = tuple(os.environ.get('GL_CHANNEL_MAP', ','.join(CHANNELS)).split(','))
    if tuple(item.strip().upper() for item in configured) != CHANNELS:
        raise ValueError('Configured GL_CHANNEL_MAP does not match the release')
    covariance = Path(os.environ.get('GL_COVARIANCE_MODEL', str(root / 'gameemo_covariance_svm.npz')))
    if covariance.resolve() != (root / 'gameemo_covariance_svm.npz').resolve():
        raise ValueError('Configured covariance model is outside the verified release')
    return len(files)


def verify_models(root, scratch):
    # Constructors check the same model contracts as the live service. Shadow
    # constructors publish only into the temporary self-test directory.
    from cyton_guardianloop import DEFAULT_CHANNEL_MAP
    from cyton_covariance import CovarianceSVM, CovarianceFeatureStream
    from cyton_fatigue import FourChannelFatigue
    from cyton_sqi import CausalEEGFilter, CytonSQIMonitor
    from seed_shadow import SeedShadow
    from ssvep_shadow import SSVEPShadow
    from mi_eegnet_rms import OfflineEEGNet
    from mi_service_config import MODEL_NAME, MODEL_SHA256, enabled

    if DEFAULT_CHANNEL_MAP != CHANNELS:
        raise ValueError('Installed acquisition channel map does not match the release')
    CausalEEGFilter(sample_rate_hz=250)
    CytonSQIMonitor(calibration_windows=15, sample_rate_hz=250)
    CovarianceSVM(root / 'gameemo_covariance_svm.npz')
    CovarianceFeatureStream(CHANNELS)
    FourChannelFatigue(root / 'cyton_fatigue_overlap4.json')
    SeedShadow(root / 'seed_shadow_weights.npz', CHANNELS, source='replay',
               status_path=scratch / 'seed.json')
    SSVEPShadow(root / 'ssvep_causal_protocol.json', root / 'ssvep_candidate_sos.npy',
                CHANNELS, source='replay', status_path=scratch / 'ssvep.json')
    if hashlib.sha256((root / MODEL_NAME).read_bytes()).hexdigest() != MODEL_SHA256:
        raise ValueError('Installed RMS MI model checksum mismatch')
    OfflineEEGNet(root / MODEL_NAME, allow_experimental=True)
    return {
        'filter_quality': {'backend': 'arm', 'channels': list(CHANNELS)},
        'emotion': {'backend': 'arm', 'channels': ['F3', 'F4', 'T7', 'T8', 'O1', 'O2']},
        'fatigue': {'backend': 'arm', 'channels': ['T7', 'T8', 'O1', 'O2']},
        'seed_candidate': {'backend': 'arm', 'channels': list(CHANNELS)},
        'ssvep_candidate': {'backend': 'arm', 'channels': ['O1', 'O2']},
        'mi_virtual': {'backend': 'arm', 'channels': list(CHANNELS),
                       'model_sha256': MODEL_SHA256, 'enabled_by_config': enabled(),
                       'personal_head_enabled': False, 'physical_control': False},
    }


def load_production_pl(root):
    if Path('/dev/guardianloop_dma_keeper').exists() or 'gldma_owner' in Path('/proc/modules').read_text():
        raise RuntimeError('Candidate DMA owner remains; PL reload requires a full board reboot')
    if subprocess.run(['systemctl', 'is-active', '--quiet', 'guardianloop-cyton.service'],
                      check=False).returncode == 0:
        raise RuntimeError('Acquisition must stop before the production PL is loaded')
    from pynq import Overlay
    overlay = Overlay(str(root / 'guardianloop_pynq.bit'), download=True)
    de = overlay.guardianloop_eeg_de_accel_v0_0
    hgb = overlay.guardianloop_hgb_accel_v0_0
    ids = {'de': int(de.read(0x20)), 'hgb': int(hgb.read(0x18)), 'model': int(hgb.read(0x30))}
    if ids != EXPECTED_IDS:
        raise RuntimeError('Production PL hardware identifiers do not match: ' + repr(ids))
    abi = tuple(int(hgb.read(offset)) for offset in (0x20, 0x24, 0x28, 0x2c))
    if abi != (3480, 120, 24, 30):
        raise RuntimeError('Production HGB hardware ABI does not match')
    return {'loaded': True, 'ids': {key: f'{value:08X}' for key, value in ids.items()},
            'used_by_current_cap': False, 'verified_at_startup': True}


def run(root, manifest_path, status_path):
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status = {'state': 'checking', 'stage': 'release', 'boot_id': boot_id(),
              'updated_at': time.time(), 'pl': {'loaded': False}, 'tasks': {}}
    atomic_json(status_path, status)
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        status['release_id'] = manifest['release_id']
        status['verified_files'] = verify_files(root, manifest)
        status['stage'] = 'arm_models'
        atomic_json(status_path, status)
        with tempfile.TemporaryDirectory(prefix='selftest-', dir=status_path.parent) as folder:
            status['tasks'] = verify_models(root, Path(folder))
        status['stage'] = 'pl_load'
        atomic_json(status_path, status)
        status['pl'] = load_production_pl(root)
        status.update(state='ready', stage='complete', updated_at=time.time())
        atomic_json(status_path, status)
        print('GUARDIANLOOP_STARTUP_READY ' + json.dumps(status['pl'], sort_keys=True), flush=True)
        return status
    except Exception as exc:
        status.update(state='failed', error=f'{type(exc).__name__}: {exc}', updated_at=time.time())
        atomic_json(status_path, status)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('release_manifest.json'))
    parser.add_argument('--status', type=Path, default=STATUS_PATH)
    args = parser.parse_args()
    run(Path(__file__).resolve().parent, args.manifest, args.status)


if __name__ == '__main__':
    main()
