import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from guide import Guide,HORIZONTAL_POINTS,FIVE_POINTS,POINTS

class GuideTests(unittest.TestCase):
    def test_six_second_training_does_not_advance_on_an_early_ack(self):
        g=Guide(relaxed=True,points=HORIZONTAL_POINTS,collect_seconds=6)
        g.start(0);g.tick(5);g.tick(7);g.response(0,True)
        self.assertEqual(g.tick(10).remaining,3)
        self.assertEqual(g.point,0)
        self.assertEqual(g.tick(13).point,1)

    def test_computes_only_after_all_configured_points_are_accepted(self):
        for points in (HORIZONTAL_POINTS,FIVE_POINTS,POINTS):
            g=Guide(relaxed=True,points=points);g.start(0);g.tick(5)
            for i in range(len(points)):
                collect_at=7+5*i
                self.assertEqual(g.tick(collect_at).phase,'collect')
                self.assertEqual(g.point,i)
                g.response(i,True)
                self.assertEqual(g.tick(collect_at+3).phase,'compute' if i==len(points)-1 else 'settle')
            self.assertEqual(g.point,len(points))

    def test_waiting_never_starts_itself(self):
        self.assertEqual(Guide().tick(100000).phase,"ready")

    def test_ack_does_not_shorten_minimum_look_time(self):
        g=Guide();g.start(0)
        self.assertEqual(g.tick(4.9).remaining,1)
        self.assertEqual(g.tick(5).phase,"settle")
        self.assertEqual(g.tick(6).phase,"collect")
        g.response(0,True)
        self.assertEqual(g.tick(8.9).point,0)
        self.assertEqual(g.tick(9).point,1)

    def test_no_reply_stops_at_ten_seconds(self):
        g=Guide();g.start(0);g.tick(5);g.tick(6)
        self.assertEqual(g.tick(9).phase,"waiting")
        self.assertEqual(g.tick(14.9).remaining,1)
        self.assertEqual(g.tick(15).phase,"failed")

    def test_wrong_point_ack_is_ignored(self):
        g=Guide();g.start(0);g.tick(5);g.tick(6)
        g.response(1,True)
        self.assertEqual(g.tick(9).phase,"waiting")

    def test_cancel_cannot_advance(self):
        g=Guide();g.start(0);g.tick(5);g.cancel()
        g.response(0,True)
        self.assertEqual(g.tick(100).phase,"cancelled")

    def test_no_success_without_actual_valid_samples(self):
        g=Guide();g.phase="compute";g.result(True,0)
        self.assertEqual(g.phase,"failed")
        g.phase="compute";g.result(True,12)
        self.assertEqual(g.phase,"complete")

    def test_preview_is_explicit_and_does_not_claim_calibration(self):
        g=Guide();g.start(0,preview=True)
        for t in range(50): g.tick(t)
        view=g.tick(50)
        self.assertEqual(view.phase,"complete")
        self.assertTrue(view.preview)
        self.assertIn("没有采样",view.detail)

    def test_relaxed_allows_late_point_success_without_shortening_settle(self):
        g=Guide(relaxed=True);g.start(0);g.tick(5)
        self.assertEqual(g.tick(6.9).phase,"settle")
        self.assertEqual(g.tick(7).phase,"collect")
        self.assertEqual(g.tick(15).phase,"waiting")
        g.detail="retry";g.response(0,True)
        self.assertEqual(g.tick(25).point,1)
        self.assertEqual(g.detail,"")

    def test_relaxed_times_out_and_never_ignores_rejection(self):
        g=Guide(relaxed=True);g.start(0);g.tick(5);g.tick(7)
        self.assertEqual(g.tick(39.9).remaining,1)
        self.assertEqual(g.tick(40).phase,"failed")
        g=Guide(relaxed=True);g.start(0);g.tick(5);g.tick(7)
        g.response(0,False)
        self.assertEqual(g.tick(8).phase,"failed")

if __name__=="__main__":unittest.main()
