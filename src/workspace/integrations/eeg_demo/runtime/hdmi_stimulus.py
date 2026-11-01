"""Finite native HDMI stimulus; owns scan updates, never PL loading or motors."""
import math
import os
import secrets
import threading
import time

import numpy as np
from PIL import Image, ImageDraw

from ssvep_hdmi import FREQUENCIES, H_TOTAL, POLICY, SCAN_PERIOD, V_TOTAL, ScanEvidence, delta32, pattern
from system_hdmi import (ACCENT, BOXES, CARD, FREQUENCY_BOXES, MUTED, OUTLINE, SELECTED,
                         TEXT, centered_text, rounded_box)
from native_scan import NativeStimulusScan, ERRORS


def ordinary_control_thread():
    # Match the producer on CPU0; native scans retain CPU1 and their own policy.
    tid=threading.get_native_id()
    os.sched_setaffinity(tid,{0})
    os.setpriority(os.PRIO_PROCESS,tid,-5)


class StimulusFrames:
    """Cache small corner patches, not sixteen full 720p frames."""
    def __init__(self, display):
        self.base = display.shells['drive'].copy()
        self.patches = {}
        self.keys = {}
        for hz, direction, box in FREQUENCY_BOXES:
            width, height = box[2]-box[0]+1, box[3]-box[1]+1
            for on in (False, True):
                for chosen in (False, True):
                    canvas = Image.new('RGB', (width, height), CARD)
                    draw = ImageDraw.Draw(canvas)
                    fill = (205, 222, 231) if on else (17, 31, 44)
                    # Selection keeps its accent in both phases, independently of EEG input.
                    border = ACCENT if chosen else OUTLINE
                    rounded_box(draw, (0, 0, width-1, height-1), 20, fill, border, 5)
                    ink = (9, 23, 35) if on else TEXT
                    centered_text(canvas, display.renderer, '%d Hz / %s' % (hz, direction),
                                  (0, 20, width, height-56), 44, ink)
                    centered_text(canvas, display.renderer, '投票选中' if chosen else '未选中',
                                  (0, height-58, width, height-12), 24, ink if on else MUTED)
                    if chosen:
                        draw.rectangle((12, height-9, width-13, height-4), fill=SELECTED)
                    self.patches[(hz, on, chosen)] = np.asarray(canvas)[:, :, ::-1].copy()
        # A frozen shell avoids font drawing/status I/O in the scan path.
        canvas = Image.fromarray(self.base[:, :, ::-1])
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 638, 1279, 719), fill=(10, 19, 30))
        centered_text(canvas, display.renderer, '四角频率测试 | 轮椅禁用 | 手机强制停止',
                      (20, 642, 1260, 694), 24)
        self.base = np.asarray(canvas)[:, :, ::-1].copy()
        box=BOXES[1]
        self.feedback_box=(box[0]+24,box[3]-120,box[2]-box[0]-48,96)
        self.feedback_states=[('idle',0),('reading',0),('lost',0),('locked',0),('executed',20)]
        self.feedback_states += [('dwell',step) for step in range(21)]
        patches=[]
        x,y,w,h=self.feedback_box
        for state in self.feedback_states:
            frame=self.base.copy()
            display.paint_feedback(frame,(None,state,None))
            patches.append(frame[y:y+h,x:x+w].copy())
        self.feedback_patches=np.stack(patches)

    def feedback_index(self,state):
        return self.feedback_states.index(state or ('idle',0))

    def paint(self, buffer, index, mask, selected=None, *, clock=None):
        if type(mask) is not int or not 0 <= mask <= 15 or selected not in (None, *FREQUENCIES):
            raise ValueError('Invalid local stimulus frame')
        old = self.keys.get(index)
        started = clock() if clock else None
        dirty_rows = set()
        copied_bytes = 0
        if old is None:
            np.copyto(buffer, self.base)
            copied_bytes += self.base.nbytes
        for i, (hz, _, box) in enumerate(FREQUENCY_BOXES):
            key = (bool(mask & (1 << i)), selected == hz)
            if old is None or key != old[i]:
                x0, y0, x1, y1 = box
                np.copyto(buffer[y0:y1+1, x0:x1+1], self.patches[(hz, *key)])
                copied_bytes += self.patches[(hz, *key)].nbytes
                dirty_rows.add((y0, y1+1))
        copied = clock() if clock else None
        flushed_bytes = 0
        if old is None:
            buffer.flush()
            flushed_bytes = buffer.nbytes
        else:
            # Full-width row bands are contiguous; corner ROIs are not.
            for y0, y1 in sorted(dirty_rows):
                band = buffer[y0:y1, :, :]
                band.flush()
                flushed_bytes += band.nbytes
        # Failed copies/flushes must not mark stale buffer contents as ready.
        self.keys[index] = tuple((bool(mask & (1 << i)), selected == hz)
                                 for i, hz in enumerate(FREQUENCIES))
        sizes = dict(copied_bytes=copied_bytes, flushed_bytes=flushed_bytes)
        if clock:
            sizes.update(copy_ms=(copied-started)*1000, flush_ms=(clock()-copied)*1000)
        return sizes


class ScanPump:
    """Keep two future frames ready; never write the current scan buffer."""
    def __init__(self, lib, paint, clock=time.monotonic, sleep=time.sleep):
        self.lib, self.paint, self.clock, self.sleep = lib, paint, clock, sleep
        self.origin = self.latest = None
        self.active = None
        self.prepared = {}

    def _prepare(self, index, target_counter):
        if index == self.lib.display_index():
            raise ValueError('Cannot prepare the active HDMI buffer')
        mask = pattern(delta32(target_counter, self.origin))
        self.paint(index, mask)
        if self.lib.display_frames() != self.latest:
            raise ValueError('Corner copy missed next scan')
        self.prepared[index] = (target_counter, mask)

    def begin(self):
        target = (self.lib.display_index()+1) % 3
        self.paint(target, pattern(0))
        before = self.lib.display_frames()
        if not self.lib.display_park(target) or self.lib.display_index() != target:
            raise ValueError('Initial stimulus did not latch')
        started = self.clock()
        while self.lib.display_frames() == before:
            if self.clock()-started > .05:
                raise ValueError('Initial HDMI scan stalled')
            self.sleep(.0002)
        self.origin = self.latest = self.lib.display_frames()
        self._status()
        self.active = target
        onset = self.clock()
        self.prepared.clear()
        for ahead in (1, 2):
            self._prepare((target+ahead) % 3, (self.origin+ahead) & 0xffffffff)
        return dict(origin_counter=self.origin, active_index=target,
                    presented_monotonic=onset)

    def _status(self):
        status = self.lib.display_status()
        if status & 0x80000ff1:
            raise ValueError('Stimulus DMA error/halt')
        return status

    def step(self):
        before = self.lib.display_frames()
        if before != self.latest:
            raise ValueError('Scan update deadline missed')
        if self.lib.display_index() != self.active:
            raise ValueError('HDMI buffer ownership changed')
        target_counter = (before+1) & 0xffffffff
        target = (self.active+1) % 3
        mask = pattern(delta32(target_counter, self.origin))
        if self.prepared.pop(target, None) != (target_counter, mask):
            raise ValueError('Next HDMI frame was not prepared')
        started = self.clock()
        if not self.lib.display_park(target) or self.lib.display_index() != target:
            raise ValueError('Stimulus frame did not latch')
        after = self.lib.display_frames()
        while after == before:
            if self.clock()-started > 1.5*SCAN_PERIOD:
                raise ValueError('Stimulus scan stalled')
            self.sleep(.0002)
            after = self.lib.display_frames()
        if after != target_counter:
            raise ValueError('Stimulus latched on the wrong scan')
        self.latest = after
        status = self._status()
        ack = self.clock()
        released = self.active
        self.active = target
        # The next scan is already ready. Refill the released buffer for the
        # scan after that before reports, queues or page work can consume time.
        self._prepare(released, (after+2) & 0xffffffff)
        return dict(counter_before=before, counter_after=after, target_counter=target_counter,
                    requested_index=target, active_index=target,
                    pattern_mask=mask, dma_status=status, ack_monotonic=ack)


class HdmiStimulus:
    """Native scan plus bounded ordinary-thread reports; main owns navigation/STOP."""
    def __init__(self, lib, buffers, display, bridge, clock=time.monotonic,
                 *, native_library=None, scan_factory=NativeStimulusScan, frames=None):
        self.lib, self.buffers, self.display, self.bridge = lib, buffers, display, bridge
        self.clock = clock
        self.native_library, self.scan_factory = native_library, scan_factory
        self.frames = frames if frames is not None else StimulusFrames(display)
        self.lock = threading.Lock()
        self.active = False
        self.selected = None
        self.error = None
        self.row = None
        self.session_id = self.page_id = None
        self.report_thread = None
        self.pending = None
        self.preparation_row = None
        self.next_preparation_poll = 0.
        self.countdown_started = False
        self.native_result = None
        self.report_stats = dict(count=0, max_http_ms=0., max_queue_age_ms=0.)
        self.vote_counts={hz:0 for hz in FREQUENCIES}
        self.vote_last_end=None
        self.display_only=False
        self.local_evidence=None
        self.entry_page=None
        self.recognition_retry_at=0.

    def start_on_entry(self,controller,now,*,enabled,input_ready):
        if (not enabled or controller.page!='drive' or controller.presented_page!=controller.page_id
                or now<controller.read_until or 'fatigue' in controller.alerts):return
        if self.entry_page==controller.page_id:
            if not (self.active and self.display_only and input_ready and now>=self.recognition_retry_at):return
            self.recognition_retry_at=now+2
            self.stop()
            try:self.start(controller.page_id,consent=True)
            except (OSError,ValueError):self.start(controller.page_id,consent=True,display_only=True)
            return
        self.entry_page=controller.page_id
        if not controller.arm_virtual_direction(now):return
        try:self.start(controller.page_id,consent=True,display_only=not input_ready)
        except (OSError,ValueError) as error:
            self.error=str(error)
            controller._stop(now,'hdmi_start_failed')

    def prepare(self, page_id, *, consent, record):
        if consent is not True or type(record) is not bool:
            raise ValueError('需要主动确认闪烁与录制选择')
        if self.pending or self.active:
            raise ValueError('已有四角测试或录制准备，请先停止')
        if self.display.controller.page != 'drive' or page_id != self.display.controller.page_id:
            raise ValueError('方向页已经改变，未启动')
        self.error = None
        if not record:
            self.start(page_id, consent=True)
            return
        reply=self.bridge.hdmi_command(dict(action='record_start',consent=True,
                                            frequencies=list(FREQUENCIES)))
        self.preparation_row=reply
        self.pending=dict(page_id=page_id,started=self.clock())
        self.next_preparation_poll=0.

    def start(self, page_id, *, consent, require_raw_recording=False, display_only=False):
        if self.active or self.session_id is not None:
            raise ValueError('Stop the previous HDMI session first')
        if self.display.controller.page != 'drive' or page_id != self.display.controller.page_id:
            raise ValueError('HDMI start requires the current direction page')
        if consent is not True:
            raise ValueError('Explicit flicker consent required')
        active = self.lib.Xil_In32(0x43c10060)
        totals = (self.lib.Xil_In32(0x43c10070)&0x1fff, self.lib.Xil_In32(0x43c10074)&0x1fff)
        if (active&0x1fff, (active>>16)&0x1fff) != (1280,720) or totals != (H_TOTAL,V_TOTAL):
            raise ValueError('HDMI mode differs from the verified 720p scan configuration')
        self.frames.keys.clear()
        self.display.buffer_pages.clear()
        self.pump = self.scan_factory(self.native_library, self.lib, self.frames, self.buffers)
        if display_only:
            if require_raw_recording:raise ValueError('Display-only mode cannot claim EEG recording')
            reply=dict(id=secrets.token_hex(16),policy=POLICY,display_page_id=page_id,state='awaiting_presentation')
        else:
            reply = self.bridge.hdmi_command(dict(action='start', page_id=page_id, consent=True,
                                               frequencies=list(FREQUENCIES),
                                               require_raw_recording=require_raw_recording))
        if (reply.get('policy') != POLICY or reply.get('display_page_id') != page_id
                or reply.get('state') != 'awaiting_presentation'
                or not isinstance(reply.get('id'), str) or not reply['id']):
            raise ValueError('HDMI producer identity mismatch')
        self.session_id, self.page_id = reply['id'], page_id
        self.display_only=display_only
        self.local_evidence=None
        self.error = self.row = self.selected = None
        self.native_result = None
        self.report_stats = dict(count=0, max_http_ms=0., max_queue_age_ms=0.,
                                 sent_latches=0,max_batch_latches=0,max_pending_latches=0)
        self.vote_counts={hz:0 for hz in FREQUENCIES}
        self.vote_last_end=None
        self.ended = threading.Event()
        self.started = self.last_response = self.clock()
        self.active = True
        self.countdown_started = False
        self.report_thread = threading.Thread(target=self._report, name='hdmi-latch-report', daemon=True)
        self.report_thread.start()

    def _fail(self, error):
        with self.lock:
            if self.error is None:
                self.error = str(error)
            self.row = None
        self.ended.set()
        self.pump.cancel()

    def _report(self):
        try:
            # Native admission checks inherited CPUs; create it before pinning its sender.
            presented=self.pump.begin()
            ordinary_control_thread()
            if self.display_only:
                self.local_evidence=ScanEvidence(presented['origin_counter'],
                    presented['presented_monotonic'],presented['active_index'])
            self._send_report(dict(action='presented',**presented))
            pending=[]
            while not self.ended.is_set():
                now=self.clock()
                if now-self.started>=30 or now-self.last_response>.35:
                    raise ValueError('HDMI duration or producer heartbeat expired')
                if len(pending)<8:
                    pending.extend(self.pump.read())
                    with self.lock:
                        self.report_stats['max_pending_latches']=max(
                            self.report_stats['max_pending_latches'],len(pending))
                if len(pending)<8:
                    self.ended.wait(.01)
                    continue
                batch=pending[:8];pending=pending[8:]
                self._send_report(dict(action='heartbeat',latches=batch))
        except Exception as error:
            # This worker boundary must publish native/library/transport failures.
            self._fail(error)
        finally:
            self.ended.set()
            self.pump.cancel()

    def _send_report(self,command):
        started=self.clock()
        stamp=(command['latches'][0]['ack_monotonic'] if command['action']=='heartbeat'
               else command['presented_monotonic'])
        with self.lock:
            self.report_stats['max_queue_age_ms']=max(self.report_stats['max_queue_age_ms'],
                                                     (started-stamp)*1000)
        if command['action']=='heartbeat' and not 0<=started-stamp<=.35:
            raise ValueError('HDMI latch evidence expired; no records skipped')
        if self.display_only:
            if command['action']=='heartbeat':self.local_evidence.observe(command['latches'],started)
            with self.lock:
                self.report_stats['count']+=1
                self.last_response=started
                self.pump.touch(started)
            return
        try:
            reply=self.bridge.hdmi_command(dict(command,id=self.session_id,page_id=self.page_id))
        finally:
            elapsed=(self.clock()-started)*1000
            with self.lock:
                self.report_stats['count']+=1
                self.report_stats['max_http_ms']=max(self.report_stats['max_http_ms'],elapsed)
        now=self.clock()
        if (reply.get('policy')!=POLICY or reply.get('id')!=self.session_id
                or reply.get('display_page_id')!=self.page_id or reply.get('state')!='active'
                or now-started>.3):
            raise ValueError('Stale or mismatched HDMI producer response')
        with self.lock:
            if not self.ended.is_set():
                self.row=(reply,now,now-started,None)
                self.last_response=now
                self.pump.touch(now)
                if command['action']=='heartbeat':
                    count=len(command['latches'])
                    self.report_stats['sent_latches']+=count
                    self.report_stats['max_batch_latches']=max(self.report_stats['max_batch_latches'],count)
                self._vote(reply)

    def _vote(self,reply):
        decision=reply.get('decision') or {};inp=reply.get('input') or {}
        end=decision.get('window_end_index_exclusive');hz=decision.get('top_hz')
        if (reply.get('frame_ok') is True and (reply.get('display_timing') or {}).get('ready') is True
                and inp.get('ready') is True and (inp.get('quality') or {}).get('hard_bad') is False
                and type(end) is int and (self.vote_last_end is None or end>self.vote_last_end)
                and hz in FREQUENCIES and type(inp.get('age_seconds')) in (int,float)
                and 0<=inp['age_seconds']<=.5):
            self.vote_counts[hz]+=1;self.vote_last_end=end

    def _vote_winner(self):
        highest=max(self.vote_counts.values())
        winners=[hz for hz,count in self.vote_counts.items() if count==highest]
        return winners[0] if highest and len(winners)==1 else None

    def input(self, page_id, now):
        with self.lock:
            row = self.row
            if (not self.active or self.ended.is_set() or page_id != self.page_id
                    or self.error or row is None or not math.isfinite(now-row[1])
                    or not 0 <= now-row[1] <= .35):
                return None
            return row

    def service(self, controller, now):
        if self.pending:
            if (controller.page!='drive' or controller.page_id!=self.pending['page_id']
                    or not controller.direction_armed or 'fatigue' in controller.alerts):
                self.stop()
                return
            if now>=self.next_preparation_poll:
                self.next_preparation_poll=now+.25
                try:
                    reply=self.bridge.hdmi_snapshot()
                    self.preparation_row=reply
                    recording=reply.get('recording_control') or {}
                    if recording.get('state')=='ready':
                        page=self.pending['page_id']
                        self.start(page,consent=True,require_raw_recording=True)
                        self.pending=None
                    elif recording.get('state') in ('error','complete','cancelling','stopping') or now-self.pending['started']>12:
                        raise ValueError(recording.get('error') or '同步原始录制启动超时，未闪烁')
                except (OSError,ValueError) as error:
                    self.error=str(error)
                    self.stop()
        if not self.active:
            return
        if (controller.page != 'drive' or controller.page_id != self.page_id
                or 'fatigue' in controller.alerts or self.ended.is_set()):
            self.stop()
            controller._stop(now, self.error or 'hdmi_page_or_session_closed')
        else:
            feedback=self.display.feedback(now)
            self.pump.feedback(self.frames.feedback_index(feedback[1] if feedback else None))
            if not self.countdown_started and self.row is not None:
                self.countdown_started=controller.direction_started(self.page_id, now)
            with self.lock:
                inp=(self.row[0].get('input') or {}) if self.row else {}
                fresh=(self.row is not None and 0<=now-self.row[1]<=.35 and inp.get('ready') is True)
                self.selected=self._vote_winner() if fresh else None
            self.pump.select(self.selected)

    def stop(self):
        if self.pending:
            self.pending=None
            try:
                self.preparation_row=self.bridge.hdmi_command(dict(action='record_cancel'))
            except (OSError,ValueError) as error:
                self.error=self.error or '录制停止尚未确认：'+str(error)
        if self.session_id is None:
            return
        self.ended.set()
        self.pump.cancel()
        with self.lock:
            self.row = None
        for worker in (self.report_thread,):
            if worker:
                worker.join(timeout=1.2)
                if worker.is_alive():
                    raise RuntimeError('HDMI worker did not stop; buffer ownership retained')
        result=self.pump.close()
        if result is not None:
            self.native_result={k:int(getattr(result,k)) for k in
                ('error','count','policy','priority','cpu','worker_cpu_ns','max_cycle_cpu_ns')}
            self.native_result['reason']=ERRORS[result.error]
        self.active = False
        if not self.display_only:
            try:
                self.bridge.hdmi_command(dict(action='stop', id=self.session_id, page_id=self.page_id))
            except (OSError, ValueError) as error:
                self.error = self.error or 'Producer stop failed: '+str(error)
        self.session_id = self.page_id = None
        self.display.buffer_pages.clear()

    def snapshot(self):
        with self.lock:
            row = self.row
            active = self.active and not self.ended.is_set() if self.active else False
            total=sum(self.vote_counts.values());winner=self._vote_winner()
            return dict(active=active, session_id=self.session_id, page_id=self.page_id,
                        display_only=self.display_only,
                        preparing=self.pending is not None,
                        raw_recording=(row[0] if row else self.preparation_row or {}).get('raw_recording'),
                        recording_control=(row[0] if row else self.preparation_row or {}).get('recording_control'),
                        decision_reason=row[0].get('reason') if row else
                            '无有效脑电：仅显示闪烁，不产生方向' if self.display_only else None,
                        error=self.error, timing=row[0].get('display_timing') if active and row else
                            self.local_evidence.snapshot(self.clock()) if active and self.local_evidence else None,
                        report_diagnostics=dict(self.report_stats),native_result=self.native_result,
                        votes=dict(mode='window_plurality_test_only',counts={str(hz):count for hz,count in self.vote_counts.items()},
                            unique_windows=total,plurality_hz=winner,
                            plurality_share=self.vote_counts[winner]/total if winner else None,
                            selected_hz=self.selected if active else None,
                            physical_output_enabled=False,idle_discrimination=False),
                        physical_output_enabled=False, display_verified_optically=False)

    def close(self):
        self.stop()
