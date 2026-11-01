"""Build the isolated S3 BLE variant; private Wi-Fi config stays in a private workdir."""
import argparse
from pathlib import Path
import shutil
import subprocess
from ble_compat import stage_library


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arduino-cli', required=True)
    p.add_argument('--arduino-config')
    p.add_argument('--wifi-config', type=Path, required=True)
    p.add_argument('--work-dir', type=Path, required=True)
    p.add_argument('--ble-library', type=Path, required=True,
                   help='Installed Arduino-ESP32 3.3.11 libraries/BLE; preserved unchanged.')
    args = p.parse_args()
    root = Path(__file__).resolve().parent
    work = args.work_dir.resolve()
    if root == work or root in work.parents:
        p.error('Use a private work directory outside the deliverable source folder.')
    if not args.wifi_config.is_file():
        p.error('Private WifiConfig.h is missing.')
    sketch = work / 'MultiControlS3'
    shutil.copytree(root / 'firmware' / 'MultiControlS3', sketch, dirs_exist_ok=True)
    shutil.copy2(args.wifi_config, sketch / 'WifiConfig.h')
    ble_library = stage_library(args.ble_library, work / 'libraries' / 'BLE')
    output = work / 'output'
    output.mkdir(parents=True, exist_ok=True)
    command = [args.arduino_cli, 'compile', '--jobs', '8', '--fqbn',
               'esp32:esp32:esp32s3:CDCOnBoot=cdc,USBMode=hwcdc',
               '--library', str(ble_library),
               '--build-property', 'compiler.cpp.extra_flags=-DMULTICONTROL_AUTO_START=0 -DMULTICONTROL_HAND_AUTO_START=1',
               '--output-dir', str(output)]
    if args.arduino_config:
        command += ['--config-file', args.arduino_config]
    command.append(str(sketch))
    with (work / 'compile.log').open('w', encoding='utf-8') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    print('Compiler exit:', result.returncode, '| private log:', work / 'compile.log')
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
