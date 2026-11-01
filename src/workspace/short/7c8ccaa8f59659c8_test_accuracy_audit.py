import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from accuracy_audit import AccuracyAudit, TARGETS
from guide import View


class AccuracyAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.audit = AccuracyAudit(Path(self.temp.name) / "accuracy.json")

    def present(self, now):
        view = self.audit.view(View(phase="selection"), now)
        self.audit.presented(view, now)

    def confirm(self, region, now, source=None):
        self.audit.observe(region, {"monotonic_ns": round((now if source is None else source) * 1e9)}, now)

    def test_schedule_balanced_and_interleaved(self):
        self.assertEqual(len(TARGETS), 30)
        self.assertEqual([TARGETS.count(i) for i in range(3)], [10, 10, 10])
        self.assertTrue(all(a != b for a, b in zip(TARGETS, TARGETS[1:])))

    def test_clock_starts_only_after_prompt_is_parked(self):
        self.audit.start()
        self.audit.tick(500)
        self.assertEqual(len(self.audit.rows), 0)
        self.present(501)
        self.confirm(0, 502.5)
        self.audit.tick(506)
        self.assertTrue(self.audit.rows[0]["first_correct"])
        self.assertEqual(self.audit.rows[0]["confirmations"][0]["response_ms"], 1500)

    def test_old_confirmation_does_not_score(self):
        self.audit.start()
        self.present(10)
        self.confirm(0, 10.1, source=9.9)
        self.audit.tick(15)
        self.assertTrue(self.audit.rows[0]["missed"])
        self.assertEqual(self.audit.outside_confirmations, 1)

    def test_wrong_first_cannot_be_replaced_by_later_correct(self):
        self.audit.start()
        self.present(10)
        self.confirm(2, 11.5)
        self.confirm(0, 13)
        self.audit.tick(15)
        row = self.audit.rows[0]
        self.assertFalse(row["first_correct"])
        self.assertEqual(row["wrong_confirmations"], 1)
        self.assertEqual(row["extra_confirmations"], 1)

    def test_timeout_is_not_removed_from_denominator(self):
        self.audit.start()
        for i in range(30):
            now = 10 + i * 6
            self.present(now)
            if i != 9:
                self.confirm(TARGETS[i], now + 1.5)
            self.audit.tick(now + 5)
        report = self.audit.snapshot()
        self.assertEqual(report["phase"], "complete")
        self.assertEqual(report["accuracy_all"], 29 / 30)
        self.assertEqual(report["missed"], 1)
        self.assertFalse(self.audit.start())

    def test_cancelled_run_is_not_complete(self):
        self.audit.start()
        self.present(10)
        self.audit.cancel("pause")
        report = self.audit.snapshot()
        self.assertEqual(report["phase"], "cancelled")
        self.assertIsNone(report["accuracy_all"])
        self.assertEqual(report["stop_reason"], "pause")


if __name__ == "__main__":
    unittest.main()
