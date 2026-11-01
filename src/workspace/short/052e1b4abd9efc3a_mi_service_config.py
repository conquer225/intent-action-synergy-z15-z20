"""Root-owned switch for fixed-eight-channel RMS MI and virtual control."""
import json
from pathlib import Path

CONFIG_PATH = Path('/etc/default/guardianloop-mi.json')
CHANNELS = ('F3', 'F4', 'C3', 'C4', 'T7', 'T8', 'O1', 'O2')
MODEL_NAME = 'experimental_rms_eegnet.npz'
MODEL_SHA256 = '363daf3b68da6e80495319052447ec83e06b9e3e327a1bd0ff9e6023a5b54221'
BACKEND_HOST = '0.0.0.0'
BACKEND_PORT = 9104


def enabled(path=CONFIG_PATH):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return False
    if not isinstance(value, dict) or set(value) != {'enabled'} or type(value['enabled']) is not bool:
        raise ValueError('MI configuration must contain only a boolean enabled field')
    return value['enabled']
