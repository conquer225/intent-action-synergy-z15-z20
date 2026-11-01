"""Tests for the read-only fixed-cap deployment audit."""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_board_runtime import CHANNEL_MAP, SERVICES, assess, local_contract, remote_script


class RuntimeAuditTests(unittest.TestCase):
    def test_empty_overrides_have_explicit_line_terminators(self):
        script = remote_script()
        for key in ("channel_map_override", "covariance_model_override"):
            self.assertIn("printf '" + key + "=%s\\n'", script)

    def test_local_model_contract(self):
        local = local_contract()
        self.assertEqual(local["physical_channels"], CHANNEL_MAP)
        self.assertEqual(local["fatigue_channels"], ("T7", "T8", "O1", "O2"))
        self.assertEqual(len(local["model_sha256"]["fatigue"]), 64)
        self.assertEqual(len(local["model_sha256"]["emotion"]), 64)

    def test_remote_mismatch_is_never_ready(self):
        local = local_contract()
        remote = {f"{service}.active": "active" for service in SERVICES}
        remote.update({"fatigue.sha256": local["model_sha256"]["fatigue"],
                       "emotion.sha256": "missing", "wlan0": "AP",
                       "api": {"stale": False}})
        remote.update({f"code.{name}.sha256": digest
                       for name, digest in local["code_sha256"].items()})
        result = assess(local, remote)
        self.assertFalse(result["model_and_dashboard_ready"])
        self.assertTrue(any("emotion model" in issue for issue in result["issues"]))

    def test_stale_data_is_reported_separately(self):
        local = local_contract()
        remote = {f"{service}.active": "active" for service in SERVICES}
        remote.update({f"{kind}.sha256": value
                       for kind, value in local["model_sha256"].items()})
        remote.update({f"code.{name}.sha256": digest
                       for name, digest in local["code_sha256"].items()})
        remote.update({"wlan0": "AP", "api": {"stale": True}})
        result = assess(local, remote)
        self.assertTrue(result["model_and_dashboard_ready"])
        self.assertTrue(result["acquisition_active"])
        self.assertFalse(result["data_fresh"])

    def test_wrong_environment_channel_map_is_rejected(self):
        local = local_contract()
        remote = {f"{service}.active": "active" for service in SERVICES}
        remote.update({f"{kind}.sha256": value
                       for kind, value in local["model_sha256"].items()})
        remote.update({f"code.{name}.sha256": digest
                       for name, digest in local["code_sha256"].items()})
        remote.update({"wlan0": "AP", "api": {"stale": False},
                       "channel_map_override": "FT7,FT8,CP1,CP2,P1,P2,O1,O2"})
        result = assess(local, remote)
        self.assertFalse(result["model_and_dashboard_ready"])
        self.assertTrue(any("GL_CHANNEL_MAP" in issue for issue in result["issues"]))


if __name__ == "__main__":
    unittest.main()
