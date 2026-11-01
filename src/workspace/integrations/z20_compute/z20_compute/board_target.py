"""Check the physical board identity and .bit package before touching the PL.

The Zynq IDCODE identifies the silicon, not its package or carrier revision.
Navigator identification therefore also requires the running device-tree model.
"""


def validate_bit_target(board_model, ps_idcode, bit_data):
    if 'navigator' not in board_model.lower():
        raise ValueError('unrecognized carrier; require the Navigator device-tree model')
    if ps_idcode & 0x0fffffff != 0x03727093:
        raise ValueError('Navigator target requires XC7Z020 silicon')
    if len(bit_data) < 13 or bit_data[:2] != b'\x00\x09':
        raise ValueError('invalid .bit header')
    offset = 2 + int.from_bytes(bit_data[:2], 'big') + 2
    part = None
    while offset < len(bit_data):
        tag = bit_data[offset:offset+1]
        offset += 1
        width = 4 if tag == b'e' else 2
        if tag not in (b'a', b'b', b'c', b'd', b'e') or offset+width > len(bit_data):
            raise ValueError('invalid .bit field')
        length = int.from_bytes(bit_data[offset:offset+width], 'big')
        offset += width
        if offset+length > len(bit_data):
            raise ValueError('truncated .bit field')
        if tag == b'b':
            part = bit_data[offset:offset+length].rstrip(b'\0').decode('ascii')
        if tag == b'e':
            if not length or length % 4 or offset+length != len(bit_data):
                raise ValueError('invalid .bit payload')
            normalized = (part or '').lower()
            if normalized.startswith('xc'):
                normalized = normalized[2:]
            if normalized != '7z020clg400':
                raise ValueError('Navigator requires 7z020clg400; image targets '+str(part))
            return dict(target='navigator-7020-clg400', part=part,
                        payload_offset=offset, payload_size=length)
        offset += length
    raise ValueError('missing .bit payload')
