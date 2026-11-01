"""Paired read-only web metadata timings; never opens serial or loads PL."""
import argparse
import importlib.util
import json
from pathlib import Path
import resource
import statistics
import time


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cpu_time():
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs', type=int, default=8)
    args = parser.parse_args()
    if not 2 <= args.pairs <= 20:
        parser.error('pairs must be between 2 and 20')
    root = Path(__file__).resolve().parent
    modules = {
        'reference': load('web_reference', root / 'guardianloop_web_reference.py'),
        'candidate': load('web_candidate', root / 'guardianloop_web.py'),
    }
    results = {}
    for name in ('cyton_receiver_present', 'system_status'):
        rows = {key: [] for key in modules}
        equal = []
        for pair in range(args.pairs):
            values = {}
            order = ('reference', 'candidate') if pair % 2 == 0 else ('candidate', 'reference')
            for key in order:
                start_cpu, start_wall = cpu_time(), time.monotonic()
                values[key] = getattr(modules[key], name)()
                wall, cpu = time.monotonic() - start_wall, cpu_time() - start_cpu
                rows[key].append({'cpu_including_children_ms': 1000 * cpu, 'wall_ms': 1000 * wall})
            equal.append(values['reference'] == values['candidate'])
        results[name] = {
            'paired_values_equal': equal,
            'measurements': {
                key: {'calls': len(values), 'rows': values,
                      'wall_median_ms': statistics.median(row['wall_ms'] for row in values),
                      'wall_max_ms': max(row['wall_ms'] for row in values),
                      'cpu_median_ms': statistics.median(row['cpu_including_children_ms'] for row in values)}
                for key, values in rows.items()
            },
        }
    results['scope'] = 'Alternating paired function timings in one diagnostic process; not real-time acceptance'
    results['boot'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    print(json.dumps(results))


if __name__ == '__main__':
    main()
