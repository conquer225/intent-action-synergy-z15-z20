"""Private adapter: historical brain estimates with real native eye input."""
import json
from pathlib import Path

from guardianloop_system.live_inputs import BrainInputs
from replay_backend import ReplayBridge

SOURCE = 'historical_recorded_eeg'


class HistoricalInputs(BrainInputs):
    def __init__(self, root, **kwargs):
        self.path = Path('/dev/shm')/(root.name+'-historical-monitor.json')
        self.bridge = ReplayBridge()
        super().__init__(fetch=self.replay_fetch, **kwargs)

    def replay_fetch(self, endpoint):
        if endpoint == 'ssvep-hdmi':
            return self.bridge.hdmi_snapshot()
        try:
            row = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        if (row.get('source') != SOURCE or row.get('physical_output_enabled') is not False
                or row.get('current_wearer') is not False):
            return {}
        return row

    def snapshot(self, now):
        with self.lock:
            row, _, _, error = self.rows.get('status', ({}, 0, 0, 'waiting'))
            hdmi, hstamp, _, herror = self.rows.get('ssvep-hdmi', ({}, 0, 0, 'waiting'))
        now = max(now, self.clock())
        stamp = row.get('updated_monotonic')
        fresh = (not error and row.get('source') == SOURCE and row.get('current_wearer') is False
                 and type(stamp) in (int,float) and 0 <= now-stamp <= 10)
        fatigue = (row.get('fatigue') or {}) if fresh else {}
        isolated = (not herror and 0 <= now-hstamp <= 1.5 and hdmi.get('source') == 'replay'
                    and hdmi.get('state_owner') == 'isolated_replay' and hdmi.get('accepted') is False)
        return dict(source=SOURCE, state='replay', connected=fresh,
            acquisition_available=True, live_eeg_connected=False, current_wearer=False,
            recording_id='fe30199c0eb9fedb', physical_output_enabled=False,
            fatigue=fatigue if fresh else dict(valid=False, level='unknown', state='replay_waiting'),
            emotion=fatigue.get('emotion') or dict(valid=False, state='replay_waiting'),
            waveform_uv=row.get('waveform_uv', []) if fresh else [],
            processed_samples=row.get('processed_samples', 0),
            ssvep_hdmi=hdmi if isolated else {}, transport_error=error,
            updated_monotonic=stamp, historical_eeg=True)

    def apply(self, controller, now):
        view = self.snapshot(now)
        if not view['connected']:
            if controller.monitor_labels:
                controller.monitoring_lost(now)
            controller.ssvep(None, now)
            return view
        fatigue, emotion = view['fatigue'], view['emotion']
        for kind, data in (('fatigue', fatigue), ('emotion', emotion)):
            if data.get('valid') is not True:
                controller.monitor_labels.pop(kind, None)
        seq = fatigue.get('seq')
        if seq != self.last_seq:
            self.last_seq = seq
            if fatigue.get('valid') is True:
                label = fatigue.get('level', 'unknown')
                controller.monitor('fatigue', 'severe_candidate' if label == 'severe' else label,
                                   now, source=SOURCE, qualified=True)
            if emotion.get('valid') is True:
                controller.monitor('emotion', emotion.get('class_name', emotion.get('label')),
                                   now, source=SOURCE, qualified=True)
        for kind, data in (('fatigue',fatigue),('emotion',emotion)):
            if data.get('valid') is True and kind in controller.monitor_labels:
                controller.monitor_labels[kind]['received_at'] = now
        # Historical windows never become this user's current direction intent.
        if controller.page == 'drive':
            controller.ssvep(None, now)
        return view

    def close(self):
        super().close()
        self.bridge._close_reports()
