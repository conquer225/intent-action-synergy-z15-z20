"""SSVEP direction preview only. Contains no motor/serial write transport."""
import argparse
import ipaddress
import json
import math
from pathlib import Path
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


DEFAULT_MAPPING = {8: 'forward', 10: 'backward', 12: 'left', 14: 'right'}
LEGACY_ROUTES = {'forward': '/start', 'backward': '/turn_back',
                 'left': '/turn_left', 'right': '/turn_right', 'stop': '/stop'}
POLICY = 'ssvep-free-experimental-v1'
HDMI_POLICY = 'ssvep-hdmi-experimental-v1'


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def load_mapping(path):
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(raw, dict) or set(raw) != {'8', '10', '12', '14'}:
        raise ValueError('mapping must specify exactly 8, 10, 12, 14 Hz')
    if set(raw.values()) != {'forward', 'backward', 'left', 'right'}:
        raise ValueError('mapping must assign each of the four directions once')
    return {int(key): value for key, value in raw.items()}


class DirectionPreview:
    def __init__(self, mapping=None):
        self.mapping = dict(DEFAULT_MAPPING if mapping is None else mapping)
        self.session = None
        self.last_end = None
        self.last_progress = None
        self.last_poll = None

    def _clear(self):
        self.session = None
        self.last_end = None
        self.last_progress = None

    def observe(self, snapshot, now, request_seconds=0, origin='json_fixture'):
        if not finite(now):
            self._clear()
            return self._output('stop', 'invalid_clock', origin)
        if self.last_poll is not None and now < self.last_poll:
            self._clear()
            self.last_poll = now
            return self._output('stop', 'clock_regression', origin)
        self.last_poll = now
        reason = self._check(snapshot, request_seconds)
        if reason:
            self._clear()
            return self._output('stop', reason, origin)
        session = snapshot['id']
        end = snapshot['decision']['window_end_index_exclusive']
        if session != self.session:
            self._clear()
            self.session = session
        elif self.last_end is not None and end != self.last_end and end - self.last_end != 50:
            self._clear()
            return self._output('stop', 'window_discontinuity', origin)
        if end != self.last_end:
            self.last_progress = now
            self.last_end = end
        if now - self.last_progress > .45:
            return self._output('stop', 'repeated_old_window', origin)
        return self._output(self.mapping[snapshot['result']], 'experimental_candidate_only', origin)

    def _check(self, s, request_seconds):
        if not isinstance(s, dict):
            return 'invalid_snapshot'
        if (s.get('policy') not in (POLICY, HDMI_POLICY) or s.get('source') != 'live'
                or s.get('state_owner') != 'acquisition'
                or s.get('observation_mode') != 'producer_callbacks'
                or s.get('control_enabled') is not False
                or s.get('production_eligible') is not False):
            return 'unexpected_producer_or_policy'
        if s.get('policy') == HDMI_POLICY:
            timing = s.get('display_timing')
            if (s.get('display_backend') != 'hdmi_scan' or not isinstance(timing, dict)
                    or timing.get('schema') != 'guardianloop-hdmi-latch-v1'
                    or timing.get('source') != 'hardware_latch_reports'
                    or timing.get('ready') is not True or timing.get('error') is not None
                    or type(s.get('display_page_id')) is not int):
                return 'hdmi_timing_unconfirmed'
        if not isinstance(s.get('id'), str) or not s['id']:
            return 'missing_session'
        if s.get('state') != 'active' or s.get('accepted') is not True:
            return 'no_selection_or_stopped'
        if s.get('frame_ok') is not True:
            return 'display_timing_unconfirmed'
        value = s.get('result')
        if type(value) is not int or value not in self.mapping:
            return 'invalid_frequency'
        if not isinstance(s.get('frequencies'), list) or value not in s['frequencies']:
            return 'inactive_frequency'
        inp = s.get('input')
        if not isinstance(inp, dict) or inp.get('ready') is not True:
            return 'input_not_ready'
        quality = inp.get('quality')
        if not isinstance(quality, dict) or quality.get('hard_bad') is not False:
            return 'bad_or_unknown_quality'
        age = inp.get('age_seconds')
        if (not finite(age) or age < 0 or not finite(request_seconds)
                or request_seconds < 0 or age + request_seconds > .5):
            return 'stale_or_unknown_input'
        d = s.get('decision')
        if not isinstance(d, dict) or d.get('failures') != [] or d.get('top_hz') != value:
            return 'inconsistent_decision'
        end = d.get('window_end_index_exclusive')
        if type(end) is not int or end < 500:
            return 'invalid_window_index'
        if (not finite(d.get('score')) or not .55 <= d['score'] <= 1.000001
                or not finite(d.get('margin')) or not .10 <= d['margin'] <= 1.000001):
            return 'weak_or_ambiguous_candidate'
        if type(s.get('evidence_windows')) is not int or s['evidence_windows'] < 2:
            return 'confirmation_incomplete'
        return None

    @staticmethod
    def _output(direction, reason, origin):
        return dict(mode='dry_run', evidence_origin=origin, preview_direction=direction,
                    reason=reason, legacy_route_reference=LEGACY_ROUTES[direction],
                    legacy_method_reference='POST',
                    legacy_interface_evidence='provided_backup_not_running_firmware',
                    physical_output_enabled=False, motor_command_sent=False,
                    current_motor_state='not_observed', ssvep_validated_for_driving=False)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise URLError('redirect rejected')


def validate_source_url(value):
    parts = urlsplit(value)
    if (parts.scheme != 'http' or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment or parts.path != '/api/ssvep-free'):
        raise ValueError('only read-only http://PRIVATE_IP:PORT/api/ssvep-free is allowed')
    try:
        address = ipaddress.ip_address(parts.hostname)
        port = parts.port
    except ValueError as error:
        raise ValueError('source must use a literal private/loopback IP') from error
    if not (address.is_private or address.is_loopback) or port is None:
        raise ValueError('source requires a private/loopback IP and an explicit port')
    return value


def reject_constant(value):
    raise ValueError('nonfinite JSON constant')


def read_snapshot(opener, url):
    with opener.open(Request(url, headers={'Accept': 'application/json',
                                           'Cache-Control': 'no-cache'}, method='GET'), timeout=.4) as response:
        if response.status != 200 or response.headers.get_content_type() != 'application/json':
            raise ValueError('unexpected read-only API response')
        data = response.read(65537)
    if len(data) > 65536:
        raise ValueError('snapshot exceeds size limit')
    return json.loads(data, parse_constant=reject_constant)


def demo_snapshot(hz=8, end=1000, **changes):
    s = dict(policy=POLICY, source='live', state_owner='acquisition',
             observation_mode='producer_callbacks', control_enabled=False,
             production_eligible=False, id='synthetic-session', state='active',
             accepted=True, frame_ok=True, result=hz, evidence_windows=2,
             frequencies=[8, 10, 12, 14],
             input=dict(ready=True, age_seconds=.02, quality={'hard_bad': False}),
             decision=dict(top_hz=hz, score=.8, margin=.3, failures=[],
                           window_end_index_exclusive=end))
    s.update(changes)
    return s


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--demo', action='store_true', help='synthetic cases, no network')
    mode.add_argument('--source-url', type=validate_source_url, help='read-only SSVEP API')
    mode.add_argument('--jsonl', type=Path, help='snapshots with local monotonic offsets')
    parser.add_argument('--mapping', type=Path, default=Path(__file__).with_name('mapping.json'))
    parser.add_argument('--seconds', type=float, default=30)
    args = parser.parse_args()
    if not finite(args.seconds) or not 0 < args.seconds <= 60:
        parser.error('--seconds must be between 0 and 60')
    preview = DirectionPreview(load_mapping(args.mapping))

    def emit(result):
        print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)

    if args.demo:
        for i, hz in enumerate((8, 10, 12, 14)):
            emit(preview.observe(demo_snapshot(hz, 1000 + i * 50), i * .2, origin='synthetic'))
        emit(preview.observe(demo_snapshot(accepted=False), 1, origin='synthetic'))
        emit(preview.observe(demo_snapshot(state='stopped'), 1.2, origin='synthetic'))
        emit(preview.observe(None, 1.4, origin='synthetic'))
        return
    if args.jsonl:
        with args.jsonl.open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line, parse_constant=reject_constant)
                emit(preview.observe(row['snapshot'], row['local_seconds'], origin='json_fixture'))
        return
    opener = build_opener(ProxyHandler({}), NoRedirect())
    started = time.monotonic()
    try:
        while time.monotonic() - started < args.seconds:
            sent = time.monotonic()
            read_error = None
            try:
                snapshot = read_snapshot(opener, args.source_url)
            except (OSError, URLError, ValueError) as error:
                snapshot = None
                read_error = type(error).__name__
            now = time.monotonic()
            result = preview.observe(snapshot, now, now - sent, origin='read_only_http')
            if read_error:
                result.update(reason='api_read_failed', error_type=read_error)
            emit(result)
            time.sleep(max(0, .1 - (time.monotonic() - sent)))
    except KeyboardInterrupt:
        pass
    finally:
        emit(preview.observe(None, time.monotonic(), origin='read_only_http'))


if __name__ == '__main__':
    main()
