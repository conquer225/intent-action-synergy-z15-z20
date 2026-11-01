"""Append reviewed public BLE sources to the complete EEG/eye baseline package."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile


def package(base, destination, source):
    base, destination, source = Path(base), Path(destination), Path(source)
    if base.resolve() == destination.resolve() or destination.exists():
        raise FileExistsError('Choose a new output archive; keep the baseline intact.')
    root_files = {'README.md', 'ACCEPTANCE.md', 'GLOSSARY.md', 'source_baseline.json', 'pc_tools_sources.json', 'build.py', 'ble_compat.py', 'run_tests.py', 'package_delivery.py'}
    selected = []
    for p in sorted(source.rglob('*')):
        if not p.is_file():
            continue
        rel = p.relative_to(source)
        if any(part.startswith('.') or part == '__pycache__' for part in rel.parts):
            continue
        allowed = (len(rel.parts) == 1 and p.name in root_files) or (
            rel.parts[0] in ('firmware', 'fallback_c3', 'tests') and p.suffix in ('.h', '.cpp', '.ino', '.csv', '.py'))
        allowed = allowed or (rel.parts[0] == 'pc_tools' and p.name in ('pc_client.py', 'pc_gui.py', 'mock_server.py', 'readonly_status.json'))
        allowed = allowed or (rel.parts[0] == 'report' and p.suffix in ('.md', '.json', '.txt'))
        if allowed and p.name != 'WifiConfig.h':
            selected.append((p, 'pendulum_ble_update/' + rel.as_posix()))
    with zipfile.ZipFile(base) as z:
        existing = set(z.namelist())
    names = [name for _, name in selected] + ['START_BLE_UPDATE.md', 'pendulum_ble_update/public_manifest.json']
    if existing.intersection(names):
        raise ValueError('Baseline already contains the BLE update; choose the original EEG baseline.')
    manifest = {'baseline_sha256': hashlib.sha256(base.read_bytes()).hexdigest(),
                'files': {name: hashlib.sha256(p.read_bytes()).hexdigest() for p, name in selected}}
    shutil.copyfile(base, destination)
    with zipfile.ZipFile(destination, 'a', compression=zipfile.ZIP_DEFLATED) as z:
        for p, name in selected:
            z.write(p, name)
        z.writestr('START_BLE_UPDATE.md', '# 我们意念合一：倒立摆蓝牙更新\n\n本包保留原脑电演示与眼控工程，新增倒立摆蓝牙版 S3 源码。先阅读 pendulum_ble_update/README.md 的接线、部署与回退说明；C3 路径保留停用。\n')
        z.writestr('pendulum_ble_update/public_manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = package(args.base, args.output, Path(__file__).resolve().parent)
    print('Packaged public BLE sources:', len(result['files']))
