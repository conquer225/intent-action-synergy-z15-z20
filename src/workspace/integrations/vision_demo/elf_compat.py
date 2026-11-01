"""Gate native runtime symbols against the measured Z15 libc version."""
import re


def validate_arm_runtime(data, maximum=(2, 31)):
    if (data[:6] != b'\x7fELF\x01\x01' or len(data) < 20
            or int.from_bytes(data[18:20], 'little') != 40):
        raise ValueError('Little-endian ARM ELF required')
    versions = sorted({tuple(int(x) for x in row.decode().split('.'))
                       for row in re.findall(rb'GLIBC_([0-9]+\.[0-9]+(?:\.[0-9]+)?)\x00', data)})
    for version in versions:
        if version > maximum:
            raise ValueError('Requires GLIBC_' + '.'.join(map(str, version))
                             + '; Z15 supports ' + '.'.join(map(str, maximum)))
    return versions
