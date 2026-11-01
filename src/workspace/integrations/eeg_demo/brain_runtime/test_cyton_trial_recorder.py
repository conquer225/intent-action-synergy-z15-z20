import json
import struct
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cyton_trial_recorder import TrialRecorder, atomic_json
from guardianloop_web import make_handler


class TrialRecordingTest(unittest.TestCase):
    def test_ssvep_raw_alignment_and_labels_are_not_emotion(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            recorder = TrialRecorder(tuple('ABCDEFGH'), .02235,
                root/'control.json', root/'status.json', root/'recordings')
            counters = dict(packets_seen=501, sequence_gaps=0, unresolved_gaps=0,
                            malformed_bytes=0, dropped_packets=0)
            command = dict(trial_id='1234567890abcdef', task='ssvep',
                condition='ssvep_cued_diagnostic', phase='ssvep_diagnostic',
                cue_log_path='cue.jsonl', protocol={'targets_hz':[10,0,12,0,10,12]})
            recorder.start(command, counters)
            for i in range(251):
                recorder.append([i]*8, i%256, i==50, i==50,
                                stream_index=500+i, received_at=100+i/250)
            recorder.finish('complete', dict(counters, packets_seen=751))
            saved = root/'recordings'/command['trial_id']
            metadata = json.loads((saved/'metadata.json').read_text())
            self.assertEqual(metadata['task'], 'ssvep')
            self.assertIsNone(metadata['self_report'])
            self.assertIn('not a verified neural response', metadata['label_provenance'])
            self.assertFalse(metadata['optical_onset_measured'])
            self.assertEqual(metadata['samples'], 251)
            self.assertEqual(metadata['stream_first_index'], 500)
            self.assertEqual(struct.unpack('<251Q', (saved/'stream_index_u64le.bin').read_bytes()),
                             tuple(range(500,751)))
            times = struct.unpack('<251d', (saved/'arrival_mono_f64le.bin').read_bytes())
            self.assertEqual(times[0], 100)
            self.assertEqual(times[-1], 101)
            self.assertEqual((saved/'flags_u8.bin').read_bytes()[50], 3)
            self.assertEqual((saved/'samples_i32le.bin').stat().st_size, 251*32)
            self.assertEqual((saved/'sequence_u8.bin').stat().st_size, 251)

    def test_ssvep_missing_alignment_cannot_silently_record(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            recorder=TrialRecorder(tuple('ABCDEFGH'), .02235,
                root/'control.json', root/'status.json', root/'recordings')
            counters={'packets_seen':1}
            command=dict(trial_id='1234567890abcdef', task='ssvep',
                         phase='ssvep_diagnostic', condition='ssvep_cued_diagnostic')
            recorder.start(command, counters)
            with self.assertRaises(ValueError):
                recorder.append([0]*8,0,False,False)
            self.assertEqual(recorder.active['samples'],0)
            recorder.finish('complete',counters)

    def test_browser_command_records_exact_raw_packets_and_self_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            control, status = root / "command.json", root / "state.json"
            telemetry, dashboard = root / "telemetry.json", root / "dashboard.json"
            atomic_json(telemetry, {"real": True, "updated_at": time.time()})
            recorder = TrialRecorder(tuple("ABCDEFGH"), 0.02235, control, status, root / "recordings")
            counters = dict(packets_seen=0, sequence_gaps=0, unresolved_gaps=0,
                            malformed_bytes=0, dropped_packets=0)
            handler = make_handler(dashboard, telemetry, 20, control, status)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            def request(method, payload=None):
                body = None if payload is None else json.dumps(payload).encode()
                req = Request(f"http://127.0.0.1:{server.server_port}/api/recording",
                              data=body, method=method,
                              headers={"Content-Type": "application/json"} if body else {})
                with urlopen(req, timeout=3) as response:
                    return response.status, json.load(response)

            try:
                with patch("guardianloop_web.command_ok", return_value=True):
                    status_code, accepted = request("POST", {
                        "action": "start", "participant_id": "P01", "phase": "evaluation",
                        "condition": "calm", "stimulus_note": "fixture A", "browser_time_ms": 123456789})
                    self.assertEqual(status_code, 202)
                    recorder.poll(counters)
                    self.assertEqual(request("GET")[1]["recording"]["state"], "recording")
                    trial_id = recorder.active["trial_id"]
                    for index in range(751):
                        counters["packets_seen"] += 1
                        recorder.append([index] * 8, index % 256, index == 500, index == 500)
                    recorder.record_window({"packets_seen": 751,
                                            "emotion": {"valid": True, "label": "calm"}})
                    recorder.last_poll = 0
                    status_code, _ = request("POST", {"action": "stop", "trial_id": trial_id,
                                                       "self_report": {"felt_label": "calm", "valence": 4, "arousal": 2},
                                                       "browser_time_ms": 123460789})
                    self.assertEqual(status_code, 202)
                    recorder.poll(counters)
                    state = request("GET")[1]["recording"]
                    self.assertEqual(state["state"], "complete")
                    trial = root / "recordings" / trial_id
                    metadata = json.loads((trial / "metadata.json").read_text(encoding="utf-8"))
                    self.assertEqual(metadata["samples"], 751)
                    self.assertEqual(metadata["self_report"]["felt_label"], "calm")
                    self.assertEqual(metadata["browser_ended_at_ms"], 123460789)
                    raw = (trial / "samples_i32le.bin").read_bytes()
                    self.assertEqual(len(raw), 751 * 8 * 4)
                    self.assertEqual(struct.unpack_from("<8i", raw, 500 * 32), (500,) * 8)
                    self.assertEqual((trial / "flags_u8.bin").read_bytes()[500], 3)
                    self.assertEqual(len((trial / "sequence_u8.bin").read_bytes()), 751)
                    self.assertIn('"label": "calm"', (trial / "window_results.jsonl").read_text())
                    with self.assertRaises(HTTPError) as invalid:
                        request("POST", {"action": "start", "participant_id": "../escape",
                                         "phase": "evaluation", "condition": "calm"})
                    self.assertEqual(invalid.exception.code, 400)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
