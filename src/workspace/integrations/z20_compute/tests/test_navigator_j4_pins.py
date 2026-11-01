import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from z20_compute.pin_audit import audit_constraints, read_package_pins


class NavigatorJ4PinTests(unittest.TestCase):
    def test_j4_ad_da_matches_two_vendor_examples_and_coexists_with_camera(self):
        j4 = ROOT / "hardware" / "navigator_j4_ad_da.xdc"
        camera = ROOT / "build" / "navigator" / "navigator_camera.xdc"
        audio = ROOT / "hardware" / "navigator_audio" / "navigator_audio.xdc"
        expected = {
            "da_data[0]": "Y9", "da_data[1]": "Y8", "da_data[2]": "W10",
            "da_data[3]": "W9", "da_data[4]": "V11", "da_data[5]": "V10",
            "da_data[6]": "Y13", "da_data[7]": "Y12", "da_clk": "Y11",
            "ad_data[0]": "W15", "ad_data[1]": "V15", "ad_data[2]": "Y14",
            "ad_data[3]": "W14", "ad_data[4]": "W13", "ad_data[5]": "V12",
            "ad_data[6]": "U15", "ad_data[7]": "U14", "ad_clk": "V13",
            "ad_otr": "U13",
        }
        self.assertEqual(read_package_pins(j4), expected)
        self.assertEqual(audit_constraints([camera, j4, audio]), [])
        vendor = ROOT / "build" / "reference_sources" / "suchang-ccc__alientek-zynq7020-examples" / "ZYNQ_7020_FPGA"
        for example, project, xdc in (
            ("44_top_ad_da_fft_lcd", "top_ad_da_fft_lcd", "top_ad_da_fft_lcd.xdc"),
            ("45_top_ad_da_fir_lcd", "top_ad_da_fir_lcd", "top_ad_da_fir_lcd.xdc"),
        ):
            source = vendor / example / "prj" / f"{project}.srcs" / "constrs_1" / "new" / xdc
            source_pins = read_package_pins(source)
            self.assertEqual({port: source_pins[port] for port in expected}, expected)

    def test_audio_hdmi_uses_existing_camera_tmds_pins(self):
        camera = read_package_pins(ROOT / "build" / "navigator" / "navigator_camera.xdc")
        hdmi = read_package_pins(ROOT / "hardware" / "navigator_audio" / "navigator_audio_hdmi.xdc")
        for signal in ("tmds_clk_p", "tmds_data_p[0]", "tmds_data_p[1]", "tmds_data_p[2]"):
            self.assertEqual(hdmi[signal], camera["TMDS_" + signal])
        self.assertEqual(len(hdmi), 4)

    def test_duplicate_package_pin_is_rejected(self):
        camera = ROOT / "build" / "navigator" / "navigator_camera.xdc"
        ad_da = ROOT / "hardware" / "navigator_j4_ad_da.xdc"
        collision = "set_property -dict {PACKAGE_PIN P19 IOSTANDARD LVCMOS33} [get_ports ad_clk]"
        problems = audit_constraints([camera, ad_da], extra_lines=[collision])
        self.assertTrue(any("P19" in problem for problem in problems))

    def test_missing_required_port_is_rejected(self):
        ad_da = ROOT / "hardware" / "navigator_j4_ad_da.xdc"
        pins = read_package_pins(ad_da)
        pins.pop("ad_otr")
        problems = audit_constraints([], required_ports=set(read_package_pins(ad_da)), assignments=pins)
        self.assertTrue(any("ad_otr" in problem for problem in problems))


if __name__ == "__main__":
    unittest.main()
