"""Exercise the real Tk UI with a fake serial transport; no physical board required."""
import sys
import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from screen_monitor import ScreenMonitor
from screen_protocol import parse_status
from screen_inspector import pixel_stats

STATUS = b"SCR I V0 F3 M0 C0 P00 T0 H8 G0 A1 X70 Y71 E0000 DI S0 I5640 R1 !0\r\n"


class SerialStub:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)

    def close(self):
        pass


class FirmwareSerialStub(SerialStub):
    """Model the configured-other-ROI rejection in screen_serial.sv."""
    def __init__(self, boxes):
        super().__init__()
        self.boxes = [list(box) for box in boxes]
        self.replies = bytearray()

    def write(self, data):
        super().write(data)
        if len(data) != 12:
            return
        slot = data[1]
        x, y = int.from_bytes(data[2:4], "big"), int.from_bytes(data[4:6], "big")
        w, h, dark, bright = data[6:10]
        ox, oy, ow, oh = self.boxes[1-slot][:4]
        if x < ox+ow and ox < x+w and y < oy+oh and oy < y+h:
            return
        self.boxes[slot] = [x, y, w, h, dark, bright]
        self.replies.extend(b"RCFG"+data[1:11])


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        with patch("screen_monitor.list_ports.comports", return_value=[]):
            self.app = ScreenMonitor(self.root)
        self.app.connection = SerialStub()
        self.app.handle("status", parse_status(STATUS))

    def tearDown(self):
        for job in self.root.tk.call("after", "info"):
            self.root.after_cancel(job)
        self.app.close()

    def acknowledge(self):
        self.app.handle("ack", self.app.pending[0][1:10])

    def set_boxes(self, boxes):
        for row, box in zip(self.app.settings, boxes):
            for field, value in zip(row, box):
                field.set(str(value))

    def drain_firmware(self):
        a = self.app
        for _ in range(10):
            data = bytes(a.connection.replies)
            a.connection.replies.clear()
            if not data:
                return
            for kind, value in a.decoder.feed(data):
                a.handle(kind, value)
        self.fail("ACK loop did not terminate")

    def timeout(self):
        self.app.check_ack_timeout(self.app.ack_deadline+0.01)

    def test_old_eye2_blocks_new_eye1_then_staged_update_succeeds(self):
        a = self.app
        target = [[382, 152, 43, 30, 45, 61], [440, 147, 46, 36, 45, 61]]
        a.connection = FirmwareSerialStub([[100, 200, 64, 32, 70, 140],
                                           [380, 150, 64, 32, 70, 140]])
        self.set_boxes(target)
        a.apply()
        self.drain_firmware()
        self.assertFalse(a.applied)
        self.assertEqual(len(a.connection.writes), 1)  # firmware rejected eye 1
        self.timeout()
        self.drain_firmware()
        self.assertEqual(a.connection.boxes, target)
        self.assertEqual([p[1] for p in a.connection.writes], [0, 0, 1, 0])
        self.assertTrue(a.can_calibrate())
        self.assertIn("双眼参数已确认", a.log.get("1.0", "end"))

    def test_recovery_tries_another_corner_if_old_eye2_blocks_first(self):
        a = self.app
        target = [[80, 40, 40, 30, 45, 61], [300, 40, 40, 30, 45, 61]]
        a.connection = FirmwareSerialStub([[300, 200, 64, 32, 70, 140],
                                           [0, 0, 160, 96, 70, 140]])
        self.set_boxes(target)
        a.apply()
        self.timeout()  # first corner also overlaps old eye 2
        self.drain_firmware()
        self.assertEqual(a.update_stage, "parking")
        self.assertFalse(a.applied)
        self.timeout()
        self.drain_firmware()
        self.assertTrue(a.applied)
        self.assertEqual(a.connection.boxes, target)
        self.assertEqual(len(a.connection.writes), 5)

    def test_missing_acks_stop_after_bounded_corner_attempts(self):
        a = self.app
        a.apply()
        for _ in range(5):
            self.timeout()
            self.assertFalse(a.can_calibrate())
        self.assertEqual(len(a.connection.writes), 5)
        self.assertFalse(a.pending)
        self.assertIn("未全部确认", a.message.get())
        a.handle("ack", a.connection.writes[-1][1:10])
        self.assertFalse(a.applied)

    def test_partial_recovery_failure_keeps_calibration_disabled(self):
        a = self.app
        a.apply()
        self.timeout()
        self.acknowledge()  # temporary eye 1 only
        a.preview()
        a.snapshot()
        self.assertEqual(len(a.connection.writes), 3)
        self.assertFalse(a.can_calibrate())
        self.timeout()  # eye 2 final did not ACK; no further mutation
        self.assertFalse(a.pending)
        self.assertFalse(a.applied)
        self.assertIn("临时框", a.message.get())

    def test_edits_and_disconnect_during_recovery(self):
        a = self.app
        a.apply()
        self.timeout()
        self.acknowledge()
        a.settings[0][0].set("225")
        self.acknowledge()
        self.acknowledge()
        self.assertFalse(a.applied)
        self.assertIn("有改动", a.message.get())
        a.apply()
        self.timeout()
        old_ack = a.pending[0][1:10]
        a.disconnect()
        a.handle("ack", old_ack)
        self.assertFalse(a.pending)
        self.assertFalse(a.applied)
        self.assertEqual(a.parking_candidates, [])

    def test_recovery_skips_corners_occupied_by_target_boxes(self):
        a = self.app
        self.set_boxes([[0, 0, 80, 40, 70, 140], [560, 0, 80, 40, 70, 140]])
        a.apply()
        self.timeout()
        self.assertEqual(a.pending[0][2:6], bytes((0, 0, 1, 212)))  # (0, 468)
        self.timeout()
        self.assertEqual(a.pending[0][2:6], bytes((2, 104, 1, 212)))  # (616, 468)
        self.timeout()
        self.assertFalse(a.pending)

    def test_serial_write_failure_cancels_recovery(self):
        a = self.app
        a.apply()
        self.timeout()
        with patch.object(a.connection, "write", side_effect=OSError("USB removed")):
            self.acknowledge()
        self.assertIsNone(a.connection)
        self.assertFalse(a.pending)
        self.assertFalse(a.can_calibrate())
        self.assertIn("串口发送失败", a.message.get())

    def test_ack_sequence_and_calibration_gate(self):
        a = self.app
        a.apply()
        self.assertEqual(len(a.connection.writes), 1)
        self.assertFalse(a.applied)
        a.handle("ack", b"wrong ack")
        self.assertEqual(len(a.connection.writes), 1)
        self.acknowledge()
        self.assertEqual(len(a.connection.writes), 2)
        self.acknowledge()
        self.assertTrue(a.can_calibrate())
        a.calibrate()
        self.assertEqual(a.connection.writes[-1], b"a")
        a.handle("status", parse_status(STATUS.replace(b"F3", b"F1")))
        a.calibrate()
        self.assertEqual(len(a.connection.writes), 3)
        self.assertIn("disabled", a.start_button.state())

    def test_edits_during_ack_and_reset(self):
        a = self.app
        a.apply()
        self.acknowledge()
        a.settings[0][4].set("71")
        self.acknowledge()
        self.assertFalse(a.applied)
        a.apply()
        self.acknowledge()
        self.acknowledge()
        self.assertTrue(a.applied)
        a.handle("status", parse_status(STATUS.replace(b"M0", b"M4")))
        a.handle("status", parse_status(STATUS))
        self.assertFalse(a.applied)

    def test_image_overlay_and_live_threshold_edit(self):
        a = self.app
        pixels = bytearray([100] * 76800)
        pixels[100 * 320 + 112] = 20
        pixels[100 * 320 + 113] = 200
        a.handle("image", bytes(pixels))
        self.assertEqual((a.photo.width(), a.photo.height()), (640, 480))
        a.overlay.set(True)
        a.show_image()
        self.assertEqual(a.photo.get(224, 200), (255, 70, 70))
        self.assertEqual(a.photo.get(226, 200), (65, 170, 255))
        a.settings[0][4].set("10")
        self.root.update_idletasks()
        self.assertEqual(a.photo.get(224, 200), (20, 20, 20))

    def test_events_ignore_counter_reset(self):
        a = self.app
        running = STATUS.replace(b"M0", b"M4").replace(b"C0", b"C7")
        a.handle("status", parse_status(running))
        event = running.replace(b"E0000 DI", b"E0001 DL")
        a.handle("status", parse_status(event))
        a.handle("status", parse_status(event))
        a.handle("status", parse_status(STATUS))
        log = a.log.get("1.0", "end")
        self.assertEqual(log.count("确认 #"), 1)
        self.assertIn("确认 #1：左", log)

    def test_inspector_uses_frozen_bytes_and_exports_without_overlay(self):
        a = self.app
        pixels = bytearray([100] * 76800)
        pixels[100 * 320 + 112] = 20
        a.handle("image", bytes(pixels))
        a.overlay.set(True)
        a.show_image()
        inspector = a.inspect_snapshot()
        inspector.window.withdraw()
        inspector.label.set("眼1 暗部")
        inspector.record(SimpleNamespace(x=225, y=201))
        sample = inspector.samples[0]
        self.assertEqual((sample["snapshot_x"], sample["snapshot_y"], sample["gray"]), (112, 100, 20))
        self.assertEqual((sample["vga_x"], sample["vga_y"]), (224, 200))
        self.assertEqual((sample["nearby_min"], sample["nearby_max"], sample["nearby_median"]), (20, 100, 100))
        a.handle("image", bytes([200] * 76800))
        self.assertEqual(inspector.gray[100 * 320 + 112], 20)
        with tempfile.TemporaryDirectory() as folder:
            inspector.export(folder)
            saved = tk.PhotoImage(master=self.root, file=str(Path(folder) / "raw.png"))
            self.assertEqual((saved.width(), saved.height()), (320, 240))
            self.assertEqual(saved.get(112, 100), (20, 20, 20))
            report = json.loads((Path(folder) / "samples.json").read_text(encoding="utf-8"))
            self.assertEqual(report["samples"][0], sample)
            self.assertFalse(report["context"]["settings_acknowledged_at_inspection"])
        self.assertEqual(a.connection.writes, [])
        inspector.clear_samples()
        self.assertEqual(inspector.samples, [])
        inspector.window.destroy()

    def test_pixel_probe_edges_do_not_wrap_rows(self):
        pixels = bytearray([100] * 76800)
        pixels[0], pixels[1], pixels[320], pixels[321] = 10, 20, 30, 40
        pixels[319], pixels[-1] = 255, 0
        corner = pixel_stats(pixels, 0, 0)
        self.assertEqual((corner["nearby_min"], corner["nearby_max"], corner["nearby_median"], corner["nearby_count"]), (10, 40, 25, 4))
        self.assertEqual(pixel_stats(pixels, 319, 239)["gray"], 0)
        with self.assertRaises(ValueError):
            pixel_stats(pixels, 320, 239)


if __name__ == "__main__":
    unittest.main()
