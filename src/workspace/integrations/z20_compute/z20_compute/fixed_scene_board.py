"""Run the three fixed person-dog scenes on Navigator Z20 Linux."""
import argparse
import json
from pathlib import Path
import time

from .fixed_scene_package import BoardSceneBundle, FRAME_BYTES


DEFAULT_BUNDLE = Path(__file__).resolve().parents[1] / 'bundle'


def _hardware_backend():
    from .backend import HardwareNPU
    from .linux import UioRegisters, UioDmaAllocator
    matches = {}
    for path in Path('/sys/class/uio').glob('uio*'):
        name = (path / 'name').read_text().strip()
        if name in ('navigator-mlp', 'navigator-npu-dma'):
            if name in matches:
                raise ValueError('duplicate NPU UIO name: ' + name)
            matches[name] = path
    if set(matches) != {'navigator-mlp', 'navigator-npu-dma'}:
        raise ValueError('Navigator NPU UIO devices missing; load matching CLG400 PL/DTB')
    regdev, ramdev = matches['navigator-mlp'], matches['navigator-npu-dma']
    registers = UioRegisters('/dev/' + regdev.name, regdev / 'maps/map0',
                             expected_address=0x40000000)
    try:
        pool = UioDmaAllocator('/dev/' + ramdev.name, ramdev / 'maps/map0',
                               '/proc/device-tree/reserved-memory/npu@2000000')
    except BaseException:
        registers.close()
        raise
    return HardwareNPU(registers, pool, timeout=2), registers, pool


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument('--backend', choices=('ps', 'pl'), default='pl')
    parser.add_argument('--index', type=int, default=0)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--auto-seconds', type=float, default=0,
                        help='cycle all three images at this interval, then exit')
    parser.add_argument('--keys', action='store_true',
                        help='use Navigator PS_KEY1/PS_KEY2 for previous/next')
    parser.add_argument('--hdmi', action='store_true',
                        help='take over reserved video ring and 720p display')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if not 0 <= args.index < 3 or args.auto_seconds < 0:
        parser.error('index must be 0..2 and auto-seconds must be nonnegative')
    if args.keys and (args.once or args.auto_seconds):
        parser.error('--keys cannot be combined with --once or --auto-seconds')
    backend = registers = pool = display = keys = None
    results = []
    try:
        if args.backend == 'pl':
            backend, registers, pool = _hardware_backend()
        bundle = BoardSceneBundle(args.bundle, backend=backend)
        if args.hdmi:
            from .fixed_scene_hdmi import NavigatorHDMI
            display = NavigatorHDMI()

        def show(index):
            result = bundle.evaluate(index)
            if display is not None:
                frame = (bytes((248, 248, 248)) * (FRAME_BYTES // 3) if result['display'] is None
                         else (args.bundle / result['display']).read_bytes())
                result['vdma_status'] = display.show(frame)
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)

        if args.auto_seconds:
            for index in range(3):
                show(index)
                if index != 2:
                    time.sleep(args.auto_seconds)
        elif args.once:
            show(args.index)
        elif args.keys:
            from .fixed_scene_keys import NavigatorKeys
            keys = NavigatorKeys()
            index = args.index
            show(index)
            try:
                while True:
                    delta = keys.poll()
                    if delta:
                        index = (index + delta) % 3
                        show(index)
                    time.sleep(.02)
            except KeyboardInterrupt:
                pass
        else:
            index = args.index
            while True:
                show(index)
                command = input('n=下一张 p=上一张 q=退出 > ').strip().lower()
                if command == 'q':
                    break
                if command == 'p':
                    index = (index - 1) % 3
                elif command in ('n', ''):
                    index = (index + 1) % 3
        report = dict(scope='same three registered images',
                      backend='PL_z20_mlp' if args.backend == 'pl' else 'PS_integer_reference',
                      pl_executed=args.backend == 'pl', hdmi_executed=args.hdmi,
                      results=results)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                   encoding='utf-8')
        return report
    finally:
        if keys is not None:
            keys.close()
        if display is not None:
            display.close()
        if backend is not None and not backend.poisoned:
            backend.close()
            pool.close()
            registers.close()


if __name__ == '__main__':
    main()
