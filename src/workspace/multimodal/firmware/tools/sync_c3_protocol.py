"""Stage the unchanged, existing protocol headers for Arduino sketch builds."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sketch = root / 'esp32c3' / 'PendulumBridgeC3'
for name, original in [('BridgeProtocol.h', root / 'shared' / 'BridgeProtocol.h'),
                       ('ControlProtocol.h', root / 'esp01' / 'PendulumBridge' / 'ControlProtocol.h')]:
    (sketch / name).write_bytes(original.read_bytes())
print('C3 protocol headers synchronized from existing canonical sources')
