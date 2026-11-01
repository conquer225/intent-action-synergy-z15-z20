import json
import unittest
from playback_policy import RecentSamples, recovery_reason, session_deadline


class PolicyTests(unittest.TestCase):
    def test_only_explicit_live_user_mode_has_no_deadline(self):
        self.assertIsNone(session_deadline({'user_controlled':True,'unified_system':True},True,10))
        self.assertEqual(session_deadline({'seconds':600},True,10),610)
        self.assertEqual(session_deadline({'user_controlled':'true','seconds':1000},True,10),910)
        with self.assertRaises(ValueError):session_deadline({'user_controlled':True},False,10)

    def test_long_running_display_does_not_expire_healthy_heartbeat(self):
        self.assertIsNone(recovery_reason(True,{'state':'menu','updated_monotonic':86400},86401,0))
        self.assertEqual(recovery_reason(True,{'state':'menu','updated_monotonic':1},86400,0),'display_heartbeat_expired')

    def test_startup_grace_does_not_hide_dead_or_error_process(self):
        row={'state':'starting'}
        self.assertIsNone(recovery_reason(True,row,20,0))
        self.assertEqual(recovery_reason(False,row,20,0),'display_process_exited')
        self.assertEqual(recovery_reason(True,{'state':'error'},20,0),'display_reported_error')
        self.assertEqual(recovery_reason(True,row,241,0),'display_heartbeat_expired')

    def test_diagnostics_stay_bounded_and_json_serializable(self):
        rows=RecentSamples(8)
        for i in range(10000):rows.append(i)
        self.assertLessEqual(len(rows),8)
        self.assertEqual(rows[-1],9999)
        self.assertEqual(len(rows)+rows.discarded,10000)
        self.assertEqual(json.loads(json.dumps(rows)),list(rows))


if __name__=='__main__':unittest.main()
