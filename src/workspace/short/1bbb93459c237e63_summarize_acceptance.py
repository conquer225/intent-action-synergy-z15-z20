"""Collect recorded evidence; do not promote an engineering exit code to a functional pass."""
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent


def summarize_run(folder):
    source = folder / 'report.json'
    if not source.is_file():
        return {'run': folder.name, 'collected': False}
    report = json.loads(source.read_text(encoding='utf-8'))
    result = {'run': folder.name, 'collected': True,
              'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'report': str(source), 'phases': {},
              'services_before': report['services_before']}
    for key in ('eye_exit_code', 'error', 'pl_restored', 'services_unchanged',
                'protected_files_unchanged', 'needs_attention', 'candidate_stop_sent_s', 'candidate_stop_ready_confirmed'):
        result[key] = report.get(key)
    for phase in dict.fromkeys(row['phase'] for row in report['samples']):
        rows = [row for row in report['samples'] if row['phase'] == phase]
        ages = [row['telemetry'].get('runtime', {}).get('input_age_at_snapshot_ms') for row in rows]
        ages = [age for age in ages if isinstance(age, (float, int))]
        result['phases'][phase] = {
            'sample_count': len(rows), 'input_age_sampled_max_ms': max(ages) if ages else None,
            'input_age_sampled_median_ms': statistics.median(ages) if ages else None,
            'web_errors': [row['web'] for row in rows if row['web'].get('code') != 200]}
    first, last = report['samples'][0], report['samples'][-1]
    result['counter_deltas'] = {key: last['primary'][key] - first['primary'][key]
                               for key in ('packets_seen', 'dropped_packets', 'sequence_gaps')}
    result['counter_deltas']['primary_stream_resets'] = (
        last['telemetry']['runtime']['primary_stream_resets'] - first['telemetry']['runtime']['primary_stream_resets'])
    log = (folder / 'eye.log').read_text(encoding='utf-8')
    if report.get('media'):
        result['media'] = json.JSONDecoder().raw_decode(log[log.index('{'):])[0]
    for line in log.splitlines():
        if line.startswith('worker_event='):
            event = json.loads(line.split('=', 1)[1])
            if event.get('kind') == 'result':result['eye_usb_result'] = event
    return result


def main():
    runs = [summarize_run(ROOT / 'output' / run) for run in
            ('hdmi60', 'usb60', 'media30', 'residentusb40', 'residentmedia30', 'directmedia30', 'stopusb40', 'stopready60')]
    snapshot = ROOT / 'output/snapshot_20261005_03/eye'
    candidate = ROOT / 'candidate/eye'
    changes = {}
    for path in candidate.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix in ('.py', '.c', '.h'):
            relative = path.relative_to(candidate)
            original = snapshot / relative
            if not original.exists() or path.read_bytes() != original.read_bytes():
                changes[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence = {'scope': 'Temporary isolated coexistence, not permanent deployment or recognition accuracy',
                'date': '2026-10-05', 'runs': runs, 'candidate_changed_sources': changes,
                'permanent_startup_changed': False, 'new_bitstream_generated': False,
                'new_driver_installed_or_loaded': False,
                'sampling_limit': '2-second snapshots; sampled maxima do not bound all intervening delays',
                'unverified': ['Human eye calibration/dwell control under coexistence', 'Audible speech/music',
                               'All brain models continuously predicting under valid signals',
                               'Abrupt SIGKILL/power-loss DMA lifecycle', 'Permanent startup arbitration']}
    for name in ('software_report.json', 'live_state.json', 'settled_state.json'):
        source = ROOT / 'output/boardregression49' / name
        if source.is_file():
            evidence[name] = {'path': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                              'data': json.loads(source.read_text(encoding='utf-8'))}
    output = ROOT / 'output/acceptance_summary.json'
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
