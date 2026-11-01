"""Producer-owned, display-only free SSVEP candidates; no validated idle detector."""
import json
import math
import secrets
import threading
import time
from pathlib import Path

from ssvep_cued import FREQUENCIES
from cyton_trial_recorder import read_json

POLICY = 'ssvep-free-experimental-v1'
# Provisional engineering rejection, not thresholds fitted to a human test set.
MIN_SCORE = .55
MIN_MARGIN = .10
MAX_SECONDS = 30


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


class FreeSSVEPSession:
    policy = POLICY

    def __init__(self, clock=time.monotonic, log_path=None):
        self.clock = clock
        self.log_path = Path(log_path) if log_path is not None else None
        self.lock = threading.Lock()
        self.trial = None

    def _log(self, event, now, **fields):
        if self.log_path is not None:
            row = dict(schema=self.policy, event=event, id=self.trial['id'],
                       board_monotonic_s=now, raw_recording_id=self.trial.get('raw_id'),
                       board_boot_id=self.trial.get('board_boot_id'), **fields)
            with self.log_path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')

    def _clear(self, reason):
        self.trial.update(reason=reason, result=None, candidate_hz=None,
                          evidence_start=None, evidence_windows=0)

    def _finish(self, now, reason):
        self._clear(reason)
        self.trial['state'] = 'stopped'
        self._log('stop', now, reason=reason, gate_counts=self.trial['gate_counts'])

    def _expire(self, now):
        t = self.trial
        if t and t['state'] in ('active', 'awaiting_presentation'):
            if now-t['started'] >= MAX_SECONDS:
                self._finish(now, 'session_timeout')
            elif now-t['heartbeat'] > 1.5:
                self._finish(now, 'display_heartbeat_lost')
            elif t['last_input'] is not None and now-t['last_input'] > .5:
                self._clear('no_fresh_eeg')

    def _snapshot(self, now):
        t = self.trial
        base = dict(policy=self.policy, control_enabled=False, production_eligible=False,
                    observation_mode='producer_callbacks', confidence_validated=False,
                    idle_classifier_validated=False, display_verified_optically=False,
                    min_score=MIN_SCORE, min_margin=MIN_MARGIN,
                    confirmation='two_nonoverlapping_2s_windows_with_continuous_agreement',
                    source='live', state_owner='acquisition')
        if t is None:
            return dict(base, state='idle', result=None, accepted=False)
        return dict(base, id=t['id'], state=t['state'], reason=t['reason'],
                    raw_recording_id=t['raw_id'], raw_eeg_recorded=t['raw_id'] is not None,
                    raw_capture_completeness_verified=False,
                    frequencies=t['frequencies'], result=t['result'],
                    candidate_hz=t['candidate_hz'], evidence_windows=t['evidence_windows'],
                    decision=t['decision'], gate_counts=dict(t['gate_counts']),
                    accepted=t['state']=='active' and t['result'] is not None,
                    frame_ok=t['frame_ok'], elapsed_seconds=round(now-t['started'], 3))

    def snapshot(self):
        now = self.clock()
        with self.lock:
            self._expire(now)
            return self._snapshot(now)

    def check_raw_recording(self, raw_id):
        with self.lock:
            t = self.trial
            if (t and t['state'] in ('active', 'awaiting_presentation')
                    and t['require_raw'] and raw_id != t['raw_id']):
                self._finish(self.clock(), 'raw_recording_unavailable')

    def _started(self, request):
        pass

    def command(self, request, *, raw_recording=None):
        now = self.clock()
        action = request.get('action')
        with self.lock:
            self._expire(now)
            if action == 'start':
                if self.trial and self.trial['state'] in ('active', 'awaiting_presentation'):
                    raise ValueError('自由选择会话已在运行')
                frequencies = request.get('frequencies')
                if frequencies not in ([8, 10, 12, 14], [10, 12]):
                    raise ValueError('仅支持四角 8/10/12/14 Hz 或 10/12 Hz 双目标')
                if request.get('consent') is not True:
                    raise ValueError('必须先确认闪烁注意事项')
                # There is deliberately no intended/selected target in this API.
                if any(key in request for key in ('target_hz', 'selected_hz', 'result')):
                    raise ValueError('自由选择接口不能接收期望答案')
                required = request.get('require_raw_recording') is True
                raw_id = (raw_recording or {}).get('trial_id')
                if required and not raw_id:
                    raise ValueError('同步原始录制尚未就绪；未启动闪烁')
                metadata = (read_json(Path(raw_recording['path'])/'metadata.json')
                            if raw_recording and raw_recording.get('path') else {})
                self.trial = dict(id=secrets.token_hex(16), state='awaiting_presentation',
                    started=now, presented=None, heartbeat=now, frequencies=frequencies,
                    frame_ok=False, last_input=None, last_end=None, evidence_start=None,
                    evidence_windows=0, candidate_hz=None, result=None, reason='waiting_for_display',
                    decision=None, gate_counts={}, last_diagnostic_key=None,
                    raw_id=raw_id, require_raw=required, board_boot_id=metadata.get('board_boot_id'))
                self._started(request)
                self._log('start', now, frequencies=frequencies, threshold_validation=False)
            else:
                t = self.trial
                if t is None or request.get('id') != t['id']:
                    raise ValueError('会话标识不匹配')
                if action == 'stop':
                    if t['state'] != 'stopped':
                        self._finish(now, 'user_or_display_stopped')
                elif action == 'presented':
                    onset, sent = request.get('browser_onset_ms'), request.get('browser_send_ms')
                    if (t['state'] != 'awaiting_presentation' or not finite(onset)
                            or not finite(sent) or not 0 <= onset <= sent <= onset+1000):
                        raise ValueError('呈现时间或状态无效')
                    t.update(state='active', presented=now, heartbeat=now)
                    self._clear('collecting_post_display_window')
                    self._log('presented', now, browser_onset_ms=onset,
                              browser_send_ms=sent, optical_measurement=False)
                elif action == 'heartbeat':
                    if t['state'] != 'active':
                        raise ValueError('自由选择会话未运行')
                    count, duration = request.get('frame_count'), request.get('duration_ms')
                    gap, rates = request.get('max_gap_ms'), request.get('display_hz')
                    if (type(count) is not int or count < 1 or not finite(duration)
                            or duration <= 0 or not finite(gap) or gap < 0
                            or not isinstance(rates, dict)
                            or set(rates) != {str(f) for f in t['frequencies']}
                            or any(not finite(v) or v < 0 for v in rates.values())):
                        raise ValueError('显示帧统计无效')
                    refresh = count*1000/duration
                    t['heartbeat'] = now
                    t['frame_ok'] = (duration >= 2000 and 235 <= refresh <= 245 and gap <= 8
                        and all(abs(rates[str(f)]-f) <= .75 for f in t['frequencies']))
                    if not t['frame_ok']:
                        self._clear('display_timing_unconfirmed')
                    self._log('heartbeat', now, frame_ok=t['frame_ok'], refresh_hz=refresh,
                              display_hz=rates, max_gap_ms=gap)
                else:
                    raise ValueError('未知自由选择操作')
            return self._snapshot(now)

    def observe(self, event, stale):
        with self.lock:
            self._observe(event, stale)

    def _note(self, event, now):
        t = self.trial
        key = (event.get('state'), event.get('window_end_index_exclusive'),
               event.get('updated_monotonic'))
        if key == t['last_diagnostic_key']:
            return
        t['last_diagnostic_key'] = key
        reason = t['reason']
        t['gate_counts'][reason] = t['gate_counts'].get(reason,0)+1
        scores = event.get('scores')
        scores = scores if isinstance(scores,list) and all(finite(v) for v in scores) else None
        lag = event.get('input_age_seconds')
        self._log('window_diagnostic', now, reason=reason, decision=t['decision'],
            input_state=event.get('state'), input_age_seconds=lag if finite(lag) else None,
            quality=event.get('quality'), scores=scores,
            window_end_index_exclusive=event.get('window_end_index_exclusive'),
            accepted=t['result'] is not None)

    def _observe(self, event, stale):
        now = self.clock()
        self._expire(now)
        t = self.trial
        if t is None or t['state'] != 'active':
            return
        try:
            self._decide(event, stale, now)
        finally:
            self._note(event, now)

    def _decide(self, event, stale, now):
        t = self.trial
        stamp, lag = event.get('updated_monotonic'), event.get('input_age_seconds')
        if (stale or event.get('source') != 'live' or event.get('valid') is not True
                or event.get('state') != 'candidate_only'
                or (event.get('quality') or {}).get('hard_bad') is not False
                or not finite(stamp) or not finite(lag) or not 0 <= lag <= .5
                or not 0 <= now-stamp+lag <= .5):
            t['decision'] = None
            self._clear('no_fresh_quality_passed_window')
            return
        t['last_input'] = stamp-lag
        if not t['frame_ok'] or stamp-lag < t['presented']+2.5:
            t['decision'] = None
            self._clear('waiting_for_display_and_complete_eeg_window')
            return
        start, end = event.get('window_start_index'), event.get('window_end_index_exclusive')
        scores = event.get('scores')
        if (type(start) is not int or type(end) is not int or start < 0 or end-start != 500
                or not isinstance(scores, list) or len(scores) != 4
                or any(not finite(v) or not 0 <= v <= 1.000001 for v in scores)):
            t['decision'] = None
            self._clear('invalid_window_or_scores')
            return
        if end == t['last_end']:
            return
        if t['last_end'] is not None and end-t['last_end'] != 50:
            self._clear('window_discontinuity')
        t['last_end'] = end
        ranked = sorted(range(4), key=lambda i: scores[i], reverse=True)
        frequency = FREQUENCIES[ranked[0]]
        margin = scores[ranked[0]]-scores[ranked[1]]
        failures = []
        if frequency != event.get('frequency_hz'): failures.append('winner_mismatch')
        if frequency not in t['frequencies']: failures.append('inactive_frequency')
        if scores[ranked[0]] < MIN_SCORE: failures.append('score_below_minimum')
        if margin < MIN_MARGIN: failures.append('margin_below_minimum')
        t['decision'] = dict(top_hz=frequency, score=scores[ranked[0]], margin=margin,
                             failures=failures, window_end_index_exclusive=end)
        if failures:
            self._clear('no_selection_insufficient_or_ambiguous_evidence')
        else:
            if t['candidate_hz'] != frequency or t['evidence_start'] is None:
                self._clear('collecting_nonoverlapping_confirmation')
                t.update(candidate_hz=frequency, evidence_start=end, evidence_windows=1)
            elif end-t['evidence_start'] >= 500:
                t.update(result=frequency, evidence_windows=2, reason='stable_candidate_unvalidated')
            self._log('candidate', now, frequency_hz=frequency, score=scores[ranked[0]],
                      margin=margin, window_end=end, confirmed=t['result'] is not None)
