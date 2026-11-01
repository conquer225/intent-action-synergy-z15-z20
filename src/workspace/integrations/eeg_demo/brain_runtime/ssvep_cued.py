"""Conservative, display-only cue/SSVEP pairing for one browser trial.

This is an interaction protocol, not a validated no-target detector.  The
browser's displayed-onset report is received on the board before a candidate
can count.  The 2.5 s guard covers the 2 s CCA window and scheduling jitter.
"""

import json
import math
import os
import secrets
import threading
import time
from pathlib import Path


FREQUENCIES = (8.0, 10.0, 12.0, 14.0)
MAX_TRIAL_SECONDS = 8.0
HEARTBEAT_SECONDS = 1.5
FULL_WINDOW_GUARD_SECONDS = 2.5
REQUIRED_CONSECUTIVE_WINDOWS = 3
AUDIT_SCHEMA = 'ssvep-cued-trial-v1'
BOOT_ID_PATH = Path('/proc/sys/kernel/random/boot_id')


class CuedSSVEPSession:
    def __init__(self, clock=time.monotonic, log_path=None, wall_clock=time.time,
                 boot_id=None, observation_mode='caller'):
        self.clock = clock
        self.wall_clock = wall_clock
        self.log_path = Path(log_path) if log_path is not None else None
        if boot_id is None:
            try:
                boot_id = BOOT_ID_PATH.read_text(encoding='ascii').strip()
            except OSError:
                boot_id = 'unavailable'
        self.boot_id = boot_id
        self.observation_mode = observation_mode
        self.lock = threading.Lock()
        self.trial = None

    def _log(self, event, now, trial, durable=False, **fields):
        if self.log_path is None:
            return
        row = dict(schema=AUDIT_SCHEMA, event=event, trial_id=trial['id'],
                   target_hz=trial['target_hz'], board_monotonic_s=now,
                   board_time_unix_s=self.wall_clock(), board_boot_id=self.boot_id,
                   board_wall_clock_not_used_for_alignment=True, **fields)
        if trial.get('raw_recording'):
            row['raw_recording_id'] = trial['raw_recording']['trial_id']
            row['raw_recording_path'] = trial['raw_recording']['path']
        line = json.dumps(row, ensure_ascii=False, allow_nan=False,
                          separators=(',', ':')) + '\n'
        fd = os.open(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, 'a', encoding='utf-8') as stream:
            stream.write(line)
            stream.flush()
            if durable:
                os.fsync(stream.fileno())

    def _finish(self, trial, now, state, reason):
        trial.update(state=state, reason=reason, streak=0, result=None, observed_hz=None)
        self._log('trial_end', now, trial, durable=True, reason=reason,
                  observed_windows=trial['observed_windows'],
                  missed_window_hops_lower_bound=trial['missed_window_hops'],
                  ever_matched=trial['ever_matched'],
                  frame_ok=trial['frame_ok'])

    def _record_shadow(self, trial, shadow, now):
        live = shadow.get('live') or {}
        end = live.get('window_end_index_exclusive')
        key = ((live.get('source'), live.get('state'), end) if type(end) is int
               else (live.get('source'), live.get('state'), live.get('reason'),
                     live.get('updated_monotonic')))
        if key == trial['last_logged_key']:
            return False
        previous = trial['last_logged_window']
        skipped = (max(0, (end-previous)//50-1)
                   if type(end) is int and type(previous) is int and end > previous else 0)
        reset = type(end) is int and type(previous) is int and end <= previous
        self._log('shadow_snapshot', now, trial,
                  stale=bool(shadow.get('stale')), source=live.get('source'),
                  state=live.get('state'), reason=live.get('reason'),
                  valid=live.get('valid'), frequency_hz=live.get('frequency_hz'),
                  scores=live.get('scores'), margin=live.get('margin'),
                  window_start_index=live.get('window_start_index'),
                  window_end_index_exclusive=end,
                  shadow_updated_monotonic_s=live.get('updated_monotonic'),
                  input_age_seconds=live.get('input_age_seconds'),
                  packets_seen=live.get('packets_seen'),
                  sequence_gaps=live.get('sequence_gaps'),
                  quality=live.get('quality'),
                  missed_window_hops_since_last_observation=skipped,
                  window_index_reset=reset,
                  snapshot_polling_may_skip_windows=self.observation_mode != 'producer_callbacks')
        if type(end) is int:
            trial['observed_windows'] += 1
            trial['missed_window_hops'] += skipped
            trial['last_logged_window'] = end
        trial['last_logged_key'] = key
        return True

    def command(self, request):
        action = request.get('action')
        now = self.clock()
        with self.lock:
            self._expire(now)
            if action == 'start':
                target = request.get('target_hz')
                if type(target) not in (int, float) or not math.isfinite(target) or float(target) not in FREQUENCIES + (0.0,):
                    raise ValueError('目标须为 8、10、12、14 Hz 或 0（休息）')
                if self.trial and self.trial['state'] in ('awaiting_presentation', 'active'):
                    if now-self.trial['started'] < MAX_TRIAL_SECONDS:
                        raise ValueError('已有提示会话正在进行')
                    self._finish(self.trial, now, 'finished', 'expired_before_new_trial')
                trial = dict(id=secrets.token_hex(16), target_hz=float(target),
                             state='awaiting_presentation', started=now,
                             presented=None, heartbeat=now, last_window=None,
                             last_logged_key=None, last_logged_window=None,
                             observed_windows=0, missed_window_hops=0,
                             ever_matched=False, streak=0, observed_hz=None,
                             last_input_at=None,
                             raw_recording=request.get('raw_recording'),
                             result=None, frame_ok=False, reason='waiting_for_display')
                self._log('trial_start', now, trial, durable=True,
                          cue_mode='single_target_or_rest', display_verified_optically=False,
                          eeg_window_logging=self.observation_mode,
                          raw_eeg_recorded=bool(trial['raw_recording']),
                          raw_capture_completeness_verified=False,
                          raw_alignment='service_packet_watermark_and_usb_receive_monotonic_not_optical'
                              if trial['raw_recording'] else None)
                self.trial = trial
            else:
                trial = self.trial
                if trial is None or request.get('id') != trial['id']:
                    raise ValueError('会话已不存在或标识不匹配')
                if action == 'presented':
                    if trial['state'] != 'awaiting_presentation':
                        raise ValueError('刺激已开始或会话已结束')
                    onset = request.get('browser_onset_ms')
                    sent = request.get('browser_send_ms')
                    browser_wall = request.get('browser_wall_ms')
                    if (type(onset) not in (int, float) or type(sent) not in (int, float)
                            or not math.isfinite(onset) or not math.isfinite(sent)
                            or onset < 0 or not onset <= sent <= onset+1000):
                        raise ValueError('浏览器呈现时间无效')
                    if (browser_wall is not None and
                            (type(browser_wall) not in (int, float)
                             or not math.isfinite(browser_wall) or browser_wall < 0)):
                        raise ValueError('浏览器日历时间无效')
                    self._log('presentation_receipt', now, trial, durable=True,
                              browser_onset_ms=onset, browser_send_ms=sent,
                              browser_wall_ms=browser_wall,
                              browser_wall_clock_not_verified=True,
                              onset_is_browser_raf_callback_not_optical_measurement=True)
                    trial.update(state='active', presented=now, heartbeat=now,
                                 reason='collecting_post_cue_window')
                elif action == 'heartbeat':
                    if trial['state'] != 'active':
                        raise ValueError('会话并未运行')
                    count = request.get('frame_count')
                    duration = request.get('duration_ms')
                    max_gap = request.get('max_gap_ms')
                    poor = request.get('poor_frames')
                    observed = request.get('display_hz')
                    if (type(count) is not int or type(poor) is not int or
                            type(duration) not in (int, float) or type(max_gap) not in (int, float) or
                            type(observed) not in (int, float) or
                            count < 0 or poor < 0 or poor > count or
                            not math.isfinite(duration) or not math.isfinite(max_gap) or
                            not math.isfinite(observed) or duration < 0 or max_gap < 0 or observed < 0):
                        raise ValueError('帧统计无效')
                    # A broken display cannot yield an accepted match.  These
                    # engineering limits are not a measured flicker spectrum.
                    trial['frame_ok'] = (count >= 20 and duration >= 300 and
                                         max_gap <= 50 and poor <= max(2, int(count * .05)) and
                                         (trial['target_hz'] == 0 or
                                          (duration >= 2000 and abs(observed-trial['target_hz']) <= .75)))
                    trial['heartbeat'] = now
                    if not trial['frame_ok']:
                        trial['streak'] = 0
                        trial['reason'] = 'display_timing_unreliable'
                        trial['result'] = None
                    self._log('display_heartbeat', now, trial, frame_count=count,
                              duration_ms=duration, max_gap_ms=max_gap,
                              poor_frames=poor, display_hz=observed,
                              frame_ok=trial['frame_ok'],
                              display_verified_optically=False)
                elif action == 'stop':
                    if trial['state'] in ('awaiting_presentation', 'active'):
                        reason = request.get('stop_reason', 'user_stopped')
                        if reason not in ('user_stopped', 'page_hidden',
                                          'display_complete', 'display_timing_unreliable'):
                            raise ValueError('停止原因无效')
                        self._finish(trial, now, 'stopped', reason)
                else:
                    raise ValueError('未知会话操作')
            return self._snapshot(now)

    def _snapshot(self, now):
        t = self.trial
        if t is None:
            return dict(state='idle', accepted=False, control_enabled=False,
                        observation_mode=self.observation_mode)
        return dict(id=t['id'], state=t['state'], target_hz=t['target_hz'],
                    elapsed_seconds=round(now-t['started'], 3),
                    presented=t['presented'] is not None, frame_ok=t['frame_ok'],
                    observed_hz=t['observed_hz'], streak=t['streak'],
                    accepted=t['state'] == 'active' and t['result'] == 'cue_match',
                    result=t['result'], ever_matched=t['ever_matched'],
                    observed_windows=t['observed_windows'],
                    missed_window_hops_lower_bound=t['missed_window_hops'],
                    reason=t['reason'], control_enabled=False,
                    observation_mode=self.observation_mode)

    def _expire(self, now):
        t = self.trial
        if t is None or t['state'] not in ('awaiting_presentation', 'active'):
            return
        if now-t['started'] >= MAX_TRIAL_SECONDS:
            self._finish(t, now, 'finished', 'trial_timeout')
        elif t['state'] == 'active' and now-t['heartbeat'] > HEARTBEAT_SECONDS:
            self._finish(t, now, 'stopped', 'display_heartbeat_lost')
        elif (t['state'] == 'active' and t['last_input_at'] is not None
              and now-t['last_input_at'] > .5):
            t.update(reason='no_fresh_quality_passed_window', streak=0,
                     last_window=None, observed_hz=None, result=None)

    def snapshot(self):
        """Read current state without observing or counting another EEG window."""
        now = self.clock()
        with self.lock:
            self._expire(now)
            return self._snapshot(now)

    def check_raw_recording(self, recording_id):
        """End a linked trial if its independently saved raw stream disappears."""
        with self.lock:
            t = self.trial
            if (t and t['state'] in ('awaiting_presentation', 'active')
                    and t.get('raw_recording')
                    and t['raw_recording']['trial_id'] != recording_id):
                self._finish(t, self.clock(), 'stopped', 'raw_recording_unavailable')

    def observe(self, shadow):
        now = self.clock()
        with self.lock:
            t = self.trial
            if t is None:
                return self._snapshot(now)
            self._expire(now)
            if t['state'] == 'active':
                new_shadow = self._record_shadow(t, shadow, now)
                old_reason = t['reason']
                old_result = t['result']
                if t['target_hz'] == 0:
                    t.update(reason='rest_no_control', streak=0, result=None)
                elif not t['frame_ok']:
                    t.update(reason='display_timing_unreliable', streak=0, result=None)
                elif now-t['presented'] < FULL_WINDOW_GUARD_SECONDS:
                    t.update(reason='collecting_post_cue_window', streak=0, result=None)
                else:
                    live = shadow.get('live') or {}
                    event_at = live.get('updated_monotonic')
                    lag = live.get('input_age_seconds')
                    index = live.get('window_end_index_exclusive')
                    fresh = (not shadow.get('stale') and live.get('source') == 'live' and
                             live.get('state') == 'candidate_only' and live.get('valid') is True and
                             type(event_at) in (int, float) and type(lag) in (int, float) and
                             math.isfinite(event_at) and math.isfinite(lag) and
                             0 <= lag <= .5 and event_at <= now and
                             now-(event_at-lag) <= .5 and
                             (live.get('quality') or {}).get('hard_bad') is not True and
                             event_at-lag >= t['presented']+FULL_WINDOW_GUARD_SECONDS)
                    if not fresh:
                        t.update(reason='no_fresh_quality_passed_window', streak=0,
                                 last_window=None, observed_hz=None, result=None)
                    elif type(index) is not int or index < 0:
                        t.update(reason='missing_window_index', streak=0, result=None)
                    elif t['last_window'] is not None and index < t['last_window']:
                        t.update(reason='out_of_order_window', streak=0,
                                 observed_hz=None, result=None)
                    elif index != t['last_window']:
                        t['last_input_at'] = event_at-lag
                        consecutive = t['last_window'] is not None and index-t['last_window'] == 50
                        t['last_window'] = index
                        frequency = live.get('frequency_hz')
                        t['observed_hz'] = frequency
                        t['streak'] = (t['streak']+1 if consecutive else 1) if frequency == t['target_hz'] else 0
                        t['reason'] = ('candidate_matches_cue' if frequency == t['target_hz']
                                       else 'candidate_differs_from_cue')
                        t['result'] = 'cue_match' if t['streak'] >= REQUIRED_CONSECUTIVE_WINDOWS else None
                        if t['result']:
                            t['reason'] = 'three_consecutive_matching_windows'
                            t['ever_matched'] = True
                if t['state'] == 'active' and (new_shadow or old_reason != t['reason'] or old_result != t['result']):
                    self._log('decision', now, t, reason=t['reason'],
                              accepted=t['result'] == 'cue_match',
                              streak=t['streak'], observed_hz=t['observed_hz'],
                              window_end_index_exclusive=t['last_window'],
                              frame_ok=t['frame_ok'])
            return self._snapshot(now)
