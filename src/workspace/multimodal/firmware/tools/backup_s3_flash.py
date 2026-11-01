"""Read the original S3 flash in independently retriable chunks."""
from pathlib import Path
import subprocess
import hashlib

root = Path(__file__).resolve().parents[1]
folder = root / 'records' / 's3_original_chunks_private_20261011'
folder.mkdir(exist_ok=True)
exe = 'C:/Users/conquer/AppData/Local/Arduino15/packages/esp32/tools/esptool_py/5.3.1/esptool.exe'
parts = []
for index in range(16):
    part = folder / f'{index:02d}.bin'
    for attempt in range(3):
        with (folder / f'{index:02d}_{attempt}.log').open('w') as log:
            result = subprocess.run([exe, '--chip', 'esp32s3', '--port', 'COM27', '--baud', '460800', 'read-flash', hex(index * 0x100000), '0x100000', str(part)], stdout=log, stderr=subprocess.STDOUT)
        if result.returncode == 0 and part.stat().st_size == 0x100000:
            break
    else:
        raise SystemExit(f'Backup failed at chunk {index}; do not flash')
    parts.append(part.read_bytes())
    print(f'S3 backup {index + 1}/16 chunks', flush=True)
output = root / 'records' / 's3_original_flash_private_20261011.bin'
output.write_bytes(b''.join(parts))
print(f'Backup complete: {output.stat().st_size} bytes, SHA256 {hashlib.sha256(output.read_bytes()).hexdigest()}', flush=True)
