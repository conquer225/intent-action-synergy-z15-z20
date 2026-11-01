"""HDMI-specific scan evidence; reuses the unchanged EEG decision gate."""
from ssvep_free import FreeSSVEPSession, finite

POLICY = 'ssvep-hdmi-experimental-v1'
TIMING_SCHEMA = 'guardianloop-hdmi-latch-v1'
FREQUENCIES = (8, 10, 12, 14)
# The pinned HWH's pixel clock and the measured VTC totals: one scan = 0.0165 s.
PIXEL_CLOCK = 75_000_000
H_TOTAL, V_TOTAL = 1650, 750
SCAN_PERIOD = H_TOTAL * V_TOTAL / PIXEL_CLOCK
SCAN_HZ = 1 / SCAN_PERIOD


def delta32(value, previous):
    return (value - previous) & 0xffffffff


def counter(value):
    return type(value) is int and 0 <= value <= 0xffffffff


def pattern(scan_index):
    if type(scan_index) is not int or scan_index < 0:
        raise ValueError('Nonnegative scan ordinal required')
    # Integer phase avoids drift. This is a quantized stimulus, not optical proof.
    return sum((1 - ((scan_index * 2 * hz * H_TOTAL * V_TOTAL // PIXEL_CLOCK) & 1)) << i
               for i, hz in enumerate(FREQUENCIES))


class ScanEvidence:
    def __init__(self, origin, onset, buffer_index):
        if (not counter(origin) or not finite(onset) or onset < 0
                or type(buffer_index) is not int or not 0 <= buffer_index <= 2):
            raise ValueError('Invalid HDMI origin')
        self.origin = self.latest = origin
        self.onset = self.stamp = onset
        self.buffer_index = buffer_index
        self.scans = 0
        self.failed = None
        self.transitions = [0] * 4
        self.last_mask = pattern(0)
        self.maximum_gap = 0.

    def observe(self, rows, now):
        if self.failed:
            raise ValueError('HDMI evidence failed; a new session is required')
        try:
            if not finite(now) or not isinstance(rows, list) or not 1 <= len(rows) <= 8:
                raise ValueError('HDMI report must contain 1..8 new latch records')
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError('Invalid latch record')
                before, after = row.get('counter_before'), row.get('counter_after')
                target = row.get('target_counter')
                index, active = row.get('requested_index'), row.get('active_index')
                stamp, mask, status = row.get('ack_monotonic'), row.get('pattern_mask'), row.get('dma_status')
                if (not all(counter(v) for v in (before, after, target, status))
                        or before != self.latest or delta32(after, before) != 1 or after != target):
                    raise ValueError('Skipped, repeated, reset or late HDMI scan')
                if (type(index) is not int or not 0 <= index <= 2
                        or index == self.buffer_index or type(active) is not int or active != index
                        or status & 0x80000ff1):
                    raise ValueError('HDMI buffer did not latch or DMA faulted')
                ordinal = delta32(after, self.origin)
                if type(mask) is not int or mask != pattern(ordinal):
                    raise ValueError('Presented pattern differs from hardware scan schedule')
                if (not finite(stamp) or not self.stamp < stamp <= now
                        or now-stamp > .35 or stamp-self.stamp > 1.5 * SCAN_PERIOD):
                    if finite(stamp):
                        raise ValueError('Stale, regressed or delayed latch acknowledgement '
                            '(age_ms=%.3f, ack_gap_ms=%.3f)' % ((now-stamp)*1000,(stamp-self.stamp)*1000))
                    raise ValueError('Stale, regressed or delayed latch acknowledgement')
                self.maximum_gap = max(self.maximum_gap, stamp-self.stamp)
                for i in range(4):
                    self.transitions[i] += bool((mask ^ self.last_mask) & (1 << i))
                self.latest, self.stamp, self.last_mask = after, stamp, mask
                self.buffer_index = active
                self.scans += 1
            elapsed = self.stamp-self.onset
            if elapsed >= 2 and abs(self.scans/elapsed - SCAN_HZ) > .4:
                raise ValueError('HDMI rate differs from the verified scan configuration')
        except (ValueError, TypeError) as error:
            self.failed = str(error)
            raise ValueError(self.failed) from error

    def snapshot(self, now):
        elapsed = self.stamp-self.onset
        fresh = finite(now) and 0 <= now-self.stamp <= .35
        ready = (not self.failed and fresh and elapsed >= 2 and self.scans >= 120
                 and abs(self.scans/elapsed-SCAN_HZ) <= .4
                 and all(abs(n/(2*elapsed)-hz) <= .3
                         for n, hz in zip(self.transitions, FREQUENCIES)))
        return dict(schema=TIMING_SCHEMA, source='hardware_latch_reports',
                    ready=bool(ready), error=self.failed, scans=self.scans,
                    scan_hz=self.scans/elapsed if elapsed else None,
                    nominal_scan_hz=SCAN_HZ, counter=self.latest,
                    updated_monotonic=self.stamp, maximum_ack_gap_ms=self.maximum_gap*1000,
                    display_hz={str(hz): n/(2*elapsed) if elapsed else 0.
                                for n, hz in zip(self.transitions, FREQUENCIES)},
                    display_verified_optically=False, phase_quantized=True)


class HdmiSSVEPSession(FreeSSVEPSession):
    policy = POLICY

    def __init__(self, clock, log_path=None):
        self.evidence = None
        self.page_id = None
        super().__init__(clock=clock, log_path=log_path)

    def _started(self, request):
        self.evidence = None
        self.page_id = request['page_id']
        self.logged_heartbeat = -float('inf')

    def _expire(self, now):
        super()._expire(now)
        t = self.trial
        if t and t['state'] == 'active' and now-t['heartbeat'] > .4:
            self._finish(now, 'hdmi_report_expired')
        elif t and t['state'] == 'active' and self.evidence and not self.evidence.snapshot(now)['ready']:
            t['frame_ok'] = False
            self._clear('waiting_for_fresh_hdmi_scan_evidence')

    def _snapshot(self, now):
        view = super()._snapshot(now)
        timing = self.evidence.snapshot(now) if self.evidence else {'ready': False}
        if not timing['ready']:
            view.update(frame_ok=False, accepted=False, result=None)
        return dict(view, display_backend='hdmi_scan', display_page_id=self.page_id,
                    display_timing=timing)

    def command(self, request, *, raw_recording=None):
        if not isinstance(request, dict):
            raise ValueError('HDMI command must be an object')
        if any(k in request for k in ('browser_onset_ms', 'browser_send_ms', 'frame_count',
                                      'duration_ms', 'display_hz', 'target_hz', 'selected_hz', 'result')):
            raise ValueError('HDMI rejects browser timing and expected EEG answers')
        action = request.get('action')
        if action == 'start':
            page = request.get('page_id')
            if type(page) is not int or page < 0 or request.get('frequencies') != list(FREQUENCIES):
                raise ValueError('HDMI requires a page identity and all four frequencies')
            return super().command(request, raw_recording=raw_recording)
        if action == 'stop':
            return super().command(request)
        with self.lock:
            now = self.clock()
            self._expire(now)
            t = self.trial
            if not t or request.get('id') != t['id'] or request.get('page_id') != self.page_id:
                raise ValueError('HDMI session/page identity mismatch')
            if action == 'presented':
                stamp = request.get('presented_monotonic')
                if (t['state'] != 'awaiting_presentation' or not finite(stamp)
                        or not 0 <= now-stamp <= .2):
                    age='%.3f' % ((now-stamp)*1000) if finite(stamp) else 'invalid'
                    raise ValueError('Invalid or stale HDMI presentation (age_ms='+age+', state='+t['state']+')')
                self.evidence = ScanEvidence(request.get('origin_counter'), stamp,
                                             request.get('active_index'))
                t.update(state='active', presented=now, heartbeat=now)
                self._clear('collecting_post_display_window')
                self._log('presented', now, hardware_origin=request['origin_counter'],
                          display_page_id=self.page_id, optical_measurement=False)
            elif action == 'heartbeat':
                if t['state'] != 'active' or self.evidence is None:
                    raise ValueError('HDMI session not active')
                try:
                    self.evidence.observe(request.get('latches'), now)
                    timing = self.evidence.snapshot(now)
                    t.update(heartbeat=now, frame_ok=timing['ready'])
                except ValueError:
                    t['frame_ok'] = False
                    self._clear('hdmi_latch_evidence_rejected')
                    raise
                if not t['frame_ok']:
                    self._clear('waiting_for_hdmi_scan_evidence')
                if now-self.logged_heartbeat >= 1:
                    self._log('heartbeat', now, frame_ok=t['frame_ok'], display_timing=timing)
                    self.logged_heartbeat = now
            else:
                raise ValueError('Unknown HDMI command')
            return self._snapshot(now)
