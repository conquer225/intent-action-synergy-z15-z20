"""Independent AXI-write shadow memory check for the full-chain XSim trace.

Reconstructs HP0-accepted writes; it does not claim PS7 VIP DDR visibility.
Requires the testbench's AW/W/B handshake trace, never vendor-internal signals.
"""
import argparse
import re
from pathlib import Path


AW = re.compile(r"^HP_AW addr=([0-9a-f]+) len=(\d+) size=(\d+) burst=(\d+) id=([0-9a-f]+)$")
W = re.compile(r"^HP_W data=([0-9a-f]+) strb=([0-9a-f]+) last=([01]) id=([0-9a-f]+)$", re.MULTILINE)
B = re.compile(r"^HP_B id=([0-9a-f]+) resp=([01]+) t=\d+.*$")
BASE = (0x00200000, 0x00201000, 0x00200000)


def golden_frames(path):
    rows = [line.split() for line in Path(path).read_text().splitlines()]
    if len(rows) < 160 or any(len(row) != 4 for row in rows[:160]):
        raise ValueError("Golden vector file lacks two 80-word frames")
    values = [int(row[3], 16) & ((1 << 40) - 1) for row in rows[:160]]
    signed = [value | (0xffffff << 40) if value & (1 << 39) else value for value in values]
    return (signed[:80], signed[80:160], signed[:80])


def verify(text, frames, blocked=False):
    bursts = []
    for line in text.splitlines():
        match = AW.match(line)
        if match:
            addr, length, size, kind, ident = (int(value, 16) if i in (0, 4) else int(value)
                                                for i, value in enumerate(match.groups()))
            number = len(bursts)
            frame, offset = divmod(number, 5)
            if frame >= (2 if blocked else 3) or (addr, length, size, kind) != (BASE[frame] + 128 * offset, 16, 3, 1):
                raise ValueError(f"AW address/shape mismatch at burst {number}")
            bursts.append(dict(address=addr, ident=ident, words=[], response=False))
            continue
        match = W.match(line)
        if match:
            data, strobe, last, ident = (int(match[1], 16), int(match[2], 16), int(match[3]), int(match[4], 16))
            burst = next((entry for entry in bursts if len(entry['words']) < 16), None)
            if burst is None or ident != burst['ident'] or strobe != 0xff:
                raise ValueError("W without matching AW/ID or full-byte strobe")
            frame = bursts.index(burst) // 5
            word = (bursts.index(burst) % 5) * 16 + len(burst['words'])
            if last != (word % 16 == 15) or data != frames[frame][word]:
                raise ValueError(f"W payload/TLAST mismatch frame={frame} word={word}")
            burst['words'].append(data)
            continue
        match = B.match(line)
        if match:
            ident, response = int(match[1], 16), int(match[2], 2)
            burst = next((entry for entry in bursts if not entry['response'] and len(entry['words']) == 16), None)
            if burst is None or ident != burst['ident'] or response:
                raise ValueError("B without completed W burst or non-OKAY response")
            burst['response'] = True

    expected_bursts = 10 if blocked else 15
    if len(bursts) != expected_bursts:
        raise ValueError(f"AW count {len(bursts)} != {expected_bursts}")
    expected_complete = 5 if blocked else 15
    if sum(entry['response'] for entry in bursts) != expected_complete:
        raise ValueError("B count differs from completed frame count")
    for frame in range(1 if blocked else 3):
        image = {}
        for burst in bursts[frame * 5:(frame + 1) * 5]:
            if not burst['response'] or len(burst['words']) != 16:
                raise ValueError(f"Incomplete published frame {frame}")
            for index, value in enumerate(burst['words']):
                address = burst['address'] + index * 8
                if address in image:
                    raise ValueError(f"Duplicate AXI memory address {address:08x}")
                image[address] = value
        if len(image) != 80 or [image.get(BASE[frame] + 8 * index) for index in range(80)] != frames[frame]:
            raise ValueError(f"AXI shadow memory mismatch frame {frame}")
    if blocked:
        if all(burst['response'] for burst in bursts[5:]) or 'FULL_BLOCKED_LOCKOUT_PASS' not in text:
            raise ValueError("Blocked case completed/published an unsafe frame")
    elif 'FULL_GUARDED_RECOVERY_PASS' not in text:
        raise ValueError("Missing full-chain completion marker")
    return dict(aw=len(bursts), w=sum(len(burst['words']) for burst in bursts),
                b=sum(entry['response'] for entry in bursts),
                shadow_frames=1 if blocked else 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('vectors', type=Path)
    parser.add_argument('--blocked', action='store_true')
    args = parser.parse_args()
    trace = args.trace.read_text(errors='replace')
    frames = golden_frames(args.vectors)
    result = verify(trace, frames, args.blocked)
    first = W.search(trace.replace('\r', ''))
    if first is None:
        raise ValueError("No W line to mutation-test")
    corruptions = {
        'payload': trace.replace(first.group(0), first.group(0).replace(first[1], '0000000000000001'), 1),
        'last': trace.replace(first.group(0), first.group(0).replace('last=0', 'last=1'), 1),
        'missing_response': trace.replace(next(line for line in trace.splitlines() if B.match(line)), '', 1),
    }
    for label, bad in corruptions.items():
        if bad == trace:
            raise AssertionError(f"Mutation did not change trace: {label}")
        try:
            verify(bad, frames, args.blocked)
        except ValueError:
            continue
        raise AssertionError(f"Corrupted {label} was not rejected")
    print(f"AXI_SHADOW_PASS {result} negative_tests={','.join(corruptions)}")


if __name__ == '__main__':
    main()
