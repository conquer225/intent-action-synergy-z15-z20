"""Offline ESP flash audit. Never opens serial/network or prints NVS strings."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import struct


ROUTES = ('/start', '/stop', '/turn_left', '/turn_right', '/turn_back')
PARTITION = struct.Struct('<2sBBII16sI')
CAR_FETCH = re.compile(
    r'''\bfetch\s*\(\s*(['"])(/start|/stop|/turn_left|/turn_right|/turn_back)\1'''
    r'''\s*(?:,\s*\{(?P<options>[^{}]*)\})?\s*\)''')
RELEASE_EVENTS = {'onmouseup', 'onpointerup', 'ontouchend', 'onpointercancel', 'ontouchcancel'}


def car_requests(handler, event):
    """Extract only literal fetch calls to known motor routes; never execute JS."""
    calls = []
    for match in CAR_FETCH.finditer(handler):
        options = match['options']
        method = re.search(r'''\bmethod\s*:\s*(['"])([A-Za-z]+)\1''', options or '')
        # An omitted options argument uses fetch's default. Dynamic options remain unknown.
        verb = method[2].upper() if method else ('GET' if options is None else 'unspecified')
        calls.append(dict(function='fetch', route=match[2], method=verb, event=event))
    return calls


class CarButtons(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buttons = []
        self.current = None
        self.event_names = set()
        self.external_scripts = 0

    def handle_starttag(self, tag, attrs):
        handlers = dict(attrs)
        self.event_names.update(key for key in handlers if key.startswith('on'))
        if tag == 'script' and handlers.get('src'):
            self.external_scripts += 1
        if tag == 'button':
            requests = [call for event, handler in handlers.items()
                        if event.startswith('on') and handler
                        for call in car_requests(handler, event)]
            self.current = dict(label='', routes=[route for route in ROUTES
                if any(call['route'] == route for call in requests)],
                event_names=sorted(key for key in handlers if key.startswith('on')),
                requests=requests)

    def handle_data(self, data):
        if self.current is not None:
            self.current['label'] += data

    def handle_endtag(self, tag):
        if tag == 'button' and self.current is not None:
            self.current['label'] = self.current['label'].strip()[:80]
            self.buttons.append(self.current)
            self.current = None


def audit_car_page(payload):
    title = payload.find(b'ESP32-C3 Car')
    if title < 0:
        return None
    begin = payload.rfind(b'<html', max(0, title - 4096), title)
    end = payload.find(b'</html>', title)
    if begin < 0 or not 0 < end - begin <= 20000:
        return None
    page = payload[begin:end + 7].decode('utf-8', errors='replace')
    parser = CarButtons()
    parser.feed(page)
    calls = [call for button in parser.buttons for call in button['requests']]
    return dict(
        embedded_car_buttons=parser.buttons,
        allowlisted_javascript_calls=calls,
        embedded_car_client_behavior=dict(
            evidence_scope='provided_backup_embedded_page_only',
            event_names=sorted(parser.event_names),
            external_script_count=parser.external_scripts,
            release_stop_handler_present=any(call['route'] == '/stop'
                and call['event'] in RELEASE_EVENTS for call in calls),
            periodic_timer_token_present=bool(re.search(r'\b(setInterval|setTimeout)\s*\(', page)),
            visibility_or_disconnect_event_token_present=bool(re.search(
                r'\b(visibilitychange|pagehide|beforeunload|offline)\b', page)),
            current_running_page_verified=False,
            receiver_deadman_verified=False))


def ctext(data):
    return data.split(b'\0', 1)[0].decode('utf-8', errors='replace')


def partition_tables(data):
    tables = []
    for offset in range(0, min(len(data), 0x20000), 0x1000):
        if data[offset:offset + 2] != b'\xaa\x50':
            continue
        entries = []
        raw_entries = bytearray()
        md5_ok = None
        terminated = False
        for pos in range(offset, min(offset + 0xc00, len(data)), 32):
            row = data[pos:pos + 32]
            if row == b'\xff' * 32:
                terminated = True
                break
            if len(row) != 32:
                break
            if row[:2] == b'\xeb\xeb':
                md5_ok = hashlib.md5(raw_entries).digest() == row[16:]
                continue
            magic, kind, subtype, start, size, name, flags = PARTITION.unpack(row)
            if magic != b'\xaa\x50' or size == 0 or start + size > len(data):
                break
            raw_entries.extend(row)
            entries.append(dict(name=ctext(name), type=kind, subtype=subtype,
                                offset=start, size=size, flags=flags))
        if entries and terminated:
            tables.append(dict(offset=offset, md5_valid=md5_ok, entries=entries))
    return tables


def parse_image(data, offset, limit):
    if offset + 24 > limit or data[offset] != 0xe9:
        return None
    count = data[offset + 1]
    if not 1 <= count <= 16:
        return None
    pos = offset + 24
    checksum = 0xef
    segments = []
    contents = []
    for _ in range(count):
        if pos + 8 > limit:
            return None
        address, size = struct.unpack_from('<II', data, pos)
        pos += 8
        if size > limit - pos:
            return None
        segment = data[pos:pos + size]
        for byte in segment:
            checksum ^= byte
        segments.append(dict(address=hex(address), size=size, file_offset=pos))
        contents.append(segment)
        pos += size
    # Checksum is the last byte of the next 16-byte-aligned image block.
    checksum_pos = offset + ((pos - offset) // 16 + 1) * 16 - 1
    if checksum_pos >= limit:
        return None
    end = checksum_pos + 1
    appended_hash = data[offset + 23] == 1
    hash_ok = None
    if appended_hash:
        if end + 32 > limit:
            return None
        hash_ok = hashlib.sha256(data[offset:end]).digest() == data[end:end + 32]
        end += 32
    result = dict(offset=offset, chip_id=struct.unpack_from('<H', data, offset + 12)[0],
                  entry_point=hex(struct.unpack_from('<I', data, offset + 4)[0]),
                  configured_flash_size_code=data[offset + 3] >> 4,
                  segment_count=count, segments=segments, image_size=end-offset,
                  checksum_valid=checksum == data[checksum_pos],
                  appended_sha256_valid=hash_ok,
                  image_sha256=hashlib.sha256(data[offset:end]).hexdigest())
    first = contents[0]
    if len(first) >= 256 and first[:4] == b'\x32\x54\xcd\xab':
        result['app'] = dict(version=ctext(first[16:48]), project=ctext(first[48:80]),
                             build_time=ctext(first[80:96]), build_date=ctext(first[96:112]),
                             idf_version=ctext(first[112:144]),
                             elf_sha256=first[144:176].hex())
        payload = b''.join(contents)
        result['known_routes_present'] = {
            route: payload.count(route.encode() + b'\0') for route in ROUTES
        }
        car_page = audit_car_page(payload)
        if car_page is not None:
            result.update(car_page)
        result['known_literals'] = {
            name: literal in payload for name, literal in (
                ('car_page_title', b'ESP32-C3 Car'),
                ('xiaozhi_websocket', b'wss://api.tenclass.net/xiaozhi/v1/'),
                ('xiaozhi_ota', b'https://api.tenclass.net/xiaozhi/ota/'),
                ('ssid_prefix_xiaozhi', b'Xiaozhi-'),
                ('ssid_lyx_wifi', b'LYX_WIFI'),
            )
        }
    return result


def audit(path):
    data = Path(path).read_bytes()
    tables = partition_tables(data)
    candidates = {0: len(data)}
    for table in tables:
        for entry in table['entries']:
            if entry['type'] == 0:
                candidates[entry['offset']] = entry['offset'] + entry['size']
    images = []
    for offset, limit in sorted(candidates.items()):
        image = parse_image(data, offset, limit)
        if image:
            images.append(image)
    return dict(path=str(Path(path).resolve()), size=len(data),
                sha256=hashlib.sha256(data).hexdigest(), partition_tables=tables,
                images=images, current_running_slot_verified=False,
                gpio_mapping_verified=False, command_deadman_verified=False,
                nvs_contents_inspected=False, serial_opened=False, network_accessed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+')
    parser.add_argument('--output', type=Path, help='Create a new JSON audit file; never overwrite')
    args = parser.parse_args()
    reports = [audit(path) for path in args.files]
    result = dict(files=reports, byte_identical=(len({r['sha256'] for r in reports}) == 1
                                               if len(reports) >= 2 else None))
    encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(encoded + '\n')
    print(encoded)


if __name__ == '__main__':
    main()
