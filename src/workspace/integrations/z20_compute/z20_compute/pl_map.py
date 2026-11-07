"""Map extension adapter; existing camera, modeling and HDMI owners remain in place."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pl_accel.backend import MapHardware
from pl_accel.view import MapView


def open_map_renderer():
    from .linux import UioRegisters, UioDmaAllocator
    def device(name):
        matches = [p for p in Path('/sys/class/uio').glob('uio*') if (p/'name').read_text().strip() == name]
        if len(matches) != 1:raise ValueError('expected one '+name)
        return matches[0]
    register, memory = device('navigator-map'), device('navigator-map-dma')
    registers = UioRegisters('/dev/'+register.name, register/'maps/map0', expected_address=0x83c40000)
    try:
        pool = UioDmaAllocator('/dev/'+memory.name, memory/'maps/map0',
                               '/proc/device-tree/reserved-memory/map@6000000')
    except BaseException:
        registers.close();raise
    return MapView(MapHardware(registers, pool, width=1280, height=720)), pool, registers
