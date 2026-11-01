"""Disassemble a bounded code range of the supplied LYX backup. No device IO."""
import argparse
import hashlib
from pathlib import Path
import struct
import subprocess

from audit_firmware import parse_image


BACKUP_SHA256 = 'fd27dc4ff4b582caa6fe1f640d8aa1a09dc00fb9f15e0a99a5dbdc7d60c3bb70'
DESCRIPTORS = {'/stop': 0x3fc9ab20, '/start': 0x3fc9ab30,
               '/turn_right': 0x3fc9ab40, '/turn_left': 0x3fc9ab50,
               '/turn_back': 0x3fc9ab60}
HANDLER_ENDS = {'/stop': 0x4200aace, '/start': 0x4200ab06,
                '/turn_right': 0x4200ab76, '/turn_left': 0x4200abae,
                '/turn_back': 0x4200ab3e}
OBJDUMP = r'C:\Users\lenovo\AppData\Local\Arduino15\packages\esp32\tools\esp-x32\2601\bin\xtensa-esp32s3-elf-objdump.exe'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=lambda value: int(value, 0))
    parser.add_argument('--end', type=lambda value: int(value, 0))
    parser.add_argument('--objdump', type=Path, default=Path(OBJDUMP))
    parser.add_argument('--report', type=Path, help='Create a new text report, never overwrite')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    data = (root / 'firmware_backups/provided_flash_fd27dc4f.bin').read_bytes()
    if hashlib.sha256(data).hexdigest() != BACKUP_SHA256:
        parser.error('This inspector applies only to the previously audited backup hash.')
    image = parse_image(data, 0x10000, 0x110000)
    if not image or image['chip_id'] != 9 or not image['checksum_valid'] or not image['appended_sha256_valid']:
        parser.error('Expected verified ESP32-S3 application image.')
    irom = next(row for row in image['segments'] if int(row['address'], 16) == 0x42000020)
    dram = next(row for row in image['segments'] if int(row['address'], 16) == 0x3fc9a700)
    base = int(irom['address'], 16)
    if (args.start is None) != (args.end is None):
        parser.error('--start and --end must be supplied together.')
    ranges = []
    report = ['OFFLINE BACKUP ONLY; no device IO.', f'backup_sha256={BACKUP_SHA256}']
    for route, address in DESCRIPTORS.items():
        offset = dram['file_offset'] + address - int(dram['address'], 16)
        uri, method, handler, context = struct.unpack_from('<IIII', data, offset)
        report.append(f'{route}: uri=0x{uri:x}, method_enum={method}, handler=0x{handler:x}, context=0x{context:x}')
        ranges.append((handler, HANDLER_ENDS[route]))
    if args.start is not None:
        ranges = [(args.start, args.end)]
    else:
        # Restart at each verified entry, rather than interpreting inter-function padding as code.
        ranges.append((0x4200b69c, 0x4200b756))
    if any(not base <= start < end <= base + irom['size'] or end - start > 4096
           for start, end in ranges):
        parser.error('Select at most 4096 bytes inside the verified IROM segment per range.')
    build = root / 'build'
    build.mkdir(exist_ok=True)
    binary = build / 'provided_backup_irom.bin'
    code = data[irom['file_offset']:irom['file_offset'] + irom['size']]
    if binary.exists():
        if binary.read_bytes() != code:
            parser.error('Existing extracted code differs; refusing to overwrite.')
    else:
        with binary.open('xb') as stream:
            stream.write(code)
    for start, end in ranges:
        result = subprocess.run([str(args.objdump), '-D', '-b', 'binary', '-m', 'xtensa',
            f'--adjust-vma={base}', f'--start-address={start}', f'--stop-address={end}',
            str(binary)], check=True, capture_output=True, text=True)
        report.append(result.stdout)
    report.append('OFFLINE BACKUP ANALYSIS ONLY; running firmware, GPIO wiring, and deadman remain unverified.')
    encoded = '\n'.join(report) + '\n'
    if args.report:
        with args.report.open('x', encoding='utf-8') as stream:
            stream.write(encoded)
    print(encoded)


if __name__ == '__main__':
    main()
