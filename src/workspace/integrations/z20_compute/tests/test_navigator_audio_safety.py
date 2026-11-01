import unittest
from pathlib import Path


RTL = Path(__file__).resolve().parents[1] / "hardware" / "navigator_audio" / "navigator_audio_demo.v"
HDMI_RTL = RTL.with_name("navigator_audio_hdmi.v")
PINS = RTL.with_name("navigator_audio.xdc")


class NavigatorAudioSafetyTests(unittest.TestCase):
    def test_both_standalone_tops_default_to_physically_silent_dac(self):
        source = RTL.read_text(encoding="utf-8")
        self.assertIn("parameter PLAYBACK_ENABLED = 0", source)
        self.assertIn("if (PLAYBACK_ENABLED) begin : g_playback", source)
        self.assertIn("end else begin : g_silent", source)
        self.assertIn("assign aud_dacdat = 1'b0;", source)
        self.assertNotIn("PLAYBACK_ENABLED(1)", source)

    def test_both_audio_tops_drive_active_high_beeper_low(self):
        for path in (RTL, HDMI_RTL):
            with self.subTest(top=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertIn("output beep", source)
                self.assertIn("assign beep = 1'b0;", source)
        self.assertIn("PACKAGE_PIN M14 IOSTANDARD LVCMOS33} [get_ports beep]",
                      PINS.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
