"""Synthetic scan/EEG tests only: not optical, human or driving evidence."""
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ssvep_cue_runtime import SSVEPCueBridge, SSVEPCueRuntime
from ssvep_hdmi import FREQUENCIES, POLICY, SCAN_PERIOD, ScanEvidence, pattern
from ssvep_shadow import CHANNELS, SSVEPShadow
from test_ssvep_cue_runtime import ASSETS, SOS


def latch(n, onset=100., origin=1000):
    return dict(counter_before=(origin+n-1)&0xffffffff, counter_after=(origin+n)&0xffffffff,
                target_counter=(origin+n)&0xffffffff, requested_index=n%3, active_index=n%3,
                pattern_mask=pattern(n), dma_status=0x11000, ack_monotonic=onset+n*SCAN_PERIOD)


class TimingTests(unittest.TestCase):
    def test_integer_schedule_matches_all_four_frequencies_over_1000_scans(self):
        for i,hz in enumerate(FREQUENCIES):
            masks=[bool(pattern(n)&(1<<i)) for n in range(1001)]
            count=sum(a!=b for a,b in zip(masks,masks[1:]))
            self.assertEqual(count,round(2*hz*1000*SCAN_PERIOD))
            self.assertAlmostEqual(count/(2*1000*SCAN_PERIOD),hz)
        with self.assertRaises(ValueError):pattern(-1)

    def test_ready_requires_every_latch_and_all_frequencies_and_wrap_is_valid(self):
        origin=0xfffffff0;track=ScanEvidence(origin,100.,0)
        for first in range(1,145,8):
            rows=[latch(n,origin=origin) for n in range(first,first+8)]
            now=rows[-1]['ack_monotonic']+.001
            track.observe(rows,now)
        self.assertTrue(track.snapshot(now)['ready'])
        self.assertFalse(track.snapshot(now+.36)['ready'])
        self.assertFalse(track.snapshot(now)['display_verified_optically'])

    def test_malformed_skipped_late_and_wrong_buffer_fail_sticky(self):
        cases=[dict(counter_after=1002),dict(counter_before=999),dict(target_counter=1002),
               dict(requested_index=0,active_index=0),dict(active_index=2),
               dict(dma_status=0x11001),dict(pattern_mask=0),dict(ack_monotonic=101.),
               dict(ack_monotonic=100.),dict(ack_monotonic=float('nan')),
               dict(counter_after=True),dict(pattern_mask=True)]
        for changed in cases:
            with self.subTest(changed=changed):
                track=ScanEvidence(1000,100.,0)
                with self.assertRaises(ValueError):track.observe([dict(latch(1),**changed)],101.)
                self.assertFalse(track.snapshot(101.)['ready'])
                with self.assertRaises(ValueError):track.observe([latch(1)],101.)


class HdmiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.now=100.;self.owner=SSVEPCueRuntime(self.root/'cue.jsonl',port=0,clock=lambda:self.now)
        self.bridge=SSVEPCueBridge(self.owner.server.server_port)
        self.page=7

    def tearDown(self):
        self.owner.close();self.temp.cleanup()

    def event(self,end=1000,hz=12,**changed):
        scores=[.2]*4;scores[FREQUENCIES.index(hz)]=.8
        return dict(dict(source='live',state='candidate_only',valid=True,quality={'hard_bad':False},
                         input_age_seconds=0.,updated_monotonic=self.now,scores=scores,frequency_hz=hz,
                         window_start_index=end-500,window_end_index_exclusive=end),**changed)

    def start(self):
        self.owner.observe(self.event())
        view=self.bridge.hdmi_command(dict(action='start',consent=True,page_id=self.page,
                                           frequencies=list(FREQUENCIES)))
        self.token=view['id'];self.onset=self.now;self.scan=0
        self.bridge.hdmi_command(dict(action='presented',id=self.token,page_id=self.page,
            presented_monotonic=self.onset,origin_counter=1000,active_index=0))

    def scan_to(self,target):
        wanted=math.floor((target-self.onset)/SCAN_PERIOD+1e-8)
        while self.scan<wanted:
            end=min(wanted,self.scan+8)
            rows=[latch(n,self.onset) for n in range(self.scan+1,end+1)]
            self.now=rows[-1]['ack_monotonic']+.001
            self.bridge.hdmi_command(dict(action='heartbeat',id=self.token,page_id=self.page,latches=rows))
            self.scan=end
        self.now=target

    def windows(self,hz=12,**changed):
        for i in range(11):
            self.scan_to(self.onset+3+i*.2)
            self.owner.observe(self.event(1000+50*i,hz,**changed))
        return self.bridge.hdmi_snapshot()

    def test_all_directions_require_real_producer_windows_not_gets(self):
        for hz in FREQUENCIES:
            self.start();self.scan_to(self.onset+3)
            self.owner.observe(self.event(hz=hz))
            for _ in range(20):self.assertFalse(self.bridge.hdmi_snapshot()['accepted'])
            result=self.windows(hz)
            self.assertEqual(result['result'],hz);self.assertTrue(result['accepted'])
            self.assertEqual(result['policy'],POLICY);self.assertEqual(result['display_page_id'],self.page)
            self.assertFalse(result['control_enabled']);self.assertFalse(result['production_eligible'])
            self.bridge.hdmi_command(dict(action='stop',id=self.token))

    def test_bad_eeg_stale_scan_and_stop_revoke(self):
        for change in ({'quality':{'hard_bad':True}},{'source':'replay'},{'valid':False},
                       {'scores':[.4,.4,.4,.4]},{'input_age_seconds':.6}):
            self.start();self.assertFalse(self.windows(**change)['accepted'])
            self.bridge.hdmi_command(dict(action='stop',id=self.token))
        self.start();self.assertTrue(self.windows()['accepted'])
        self.now+=.36
        self.owner.observe(self.event(1600))
        self.assertFalse(self.bridge.hdmi_snapshot()['accepted'])
        self.now+=.1
        self.assertEqual(self.bridge.hdmi_snapshot()['state'],'stopped')

    def test_cross_page_cross_session_and_browser_timing_rejected(self):
        self.start()
        command=dict(action='heartbeat',id=self.token,page_id=self.page,latches=[latch(1)])
        for change in ({'page_id':8},{'id':'old'},{'frame_count':240},{'target_hz':12}):
            with self.assertRaises(ValueError):self.bridge.hdmi_command(dict(command,**change))
        self.assertFalse(self.bridge.hdmi_snapshot()['accepted'])
        with self.assertRaises(ValueError):self.bridge.free_command(dict(action='start',consent=True,frequencies=list(FREQUENCIES)))
        with self.assertRaises(ValueError):self.bridge.command(dict(action='start',target_hz=12))
        self.bridge.hdmi_command(dict(action='stop',id=self.token))
        self.owner.observe(self.event())
        self.bridge.free_command(dict(action='start',consent=True,frequencies=list(FREQUENCIES)))
        with self.assertRaises(ValueError):self.bridge.hdmi_command(dict(action='start',consent=True,page_id=8,frequencies=list(FREQUENCIES)))

    def test_latch_failure_cannot_preserve_an_old_match(self):
        self.start();self.assertTrue(self.windows()['accepted'])
        self.now+=SCAN_PERIOD
        with self.assertRaises(ValueError):
            self.bridge.hdmi_command(dict(action='heartbeat',id=self.token,page_id=self.page,
                                           latches=[dict(latch(self.scan+1,self.onset),active_index=99)]))
        self.assertFalse(self.bridge.hdmi_snapshot()['accepted'])
        self.owner.observe(self.event(1550))
        self.assertFalse(self.bridge.hdmi_snapshot()['accepted'])

    def test_hdmi_log_failure_disables_only_hdmi_lane(self):
        self.start();self.owner.hdmi_session.log_path=self.root/'missing'/'hdmi.jsonl'
        self.owner.observe(self.event())
        self.assertTrue(self.owner.hdmi_failed)
        self.assertFalse(self.owner.free_failed);self.assertFalse(self.owner.failed)
        self.assertFalse(self.bridge.hdmi_snapshot()['accepted'])

    def test_start_without_fresh_input_or_consent_is_rejected(self):
        command=dict(action='start',consent=True,page_id=7,frequencies=list(FREQUENCIES))
        with self.assertRaises(ValueError):self.bridge.hdmi_command(command)
        self.owner.observe(self.event())
        for change in ({'consent':False},{'frequencies':[10,12]},{'page_id':True},
                       {'require_raw_recording':True},{'selected_hz':12}):
            with self.assertRaises(ValueError):self.bridge.hdmi_command(dict(command,**change))

    def test_actual_decoder_with_synthetic_raw_eeg_and_500_sample_windows(self):
        with patch('ssvep_shadow.time.monotonic',lambda:self.now):
            shadow=SSVEPShadow(ASSETS/'ssvep_causal_protocol.json',SOS,CHANNELS,
                source='live',status_path=self.root/'synthetic.json',event_sink=self.owner.observe)
            t=np.arange(2800)/250
            samples=np.zeros((len(t),8))
            samples[:,6]=12*np.sin(2*np.pi*12*t)+np.sin(2*np.pi*17*t)
            samples[:,7]=9*np.sin(2*np.pi*12*t+.3)+np.sin(2*np.pi*19*t)
            for i in range(800):
                self.now=100+i/250;shadow.packet(samples[i],i%256,now=self.now)
            self.start()
            for i in range(800,2800):
                self.scan_to(100+i/250);shadow.packet(samples[i],i%256,now=self.now)
            view=self.bridge.hdmi_snapshot()
            self.assertEqual(view['result'],12);self.assertTrue(view['accepted'])
            self.assertFalse(view['display_verified_optically'])


if __name__=='__main__':unittest.main()
