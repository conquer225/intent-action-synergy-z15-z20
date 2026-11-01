import unittest

from prewear_observe import frame_progress


def row(frame, published, polled, page='video', session='test'):
    return dict(frame=frame,updated_monotonic=published,monotonic=polled,
                state='playing',page=page,session=session)


class FrameProgressTests(unittest.TestCase):
    def test_late_poll_does_not_change_publication_frame_rate(self):
        result=frame_progress([row(0,10,10.1),row(20,11,11.8),row(40,12,12.2)])
        self.assertEqual(result['weighted_fps'],20)
        self.assertEqual(result['minimum_interval_fps'],20)
        self.assertEqual(result['intervals_below16'],0)

    def test_duplicates_keep_stall_visible_and_next_period_complete(self):
        result=frame_progress([row(0,10,10),row(0,10,11),row(0,10,12),row(20,13,13)])
        self.assertEqual(result['duplicate_publications'],2)
        self.assertEqual(result['maximum_publication_age_seconds'],2)
        self.assertAlmostEqual(result['weighted_fps'],20/3)
        self.assertEqual(result['intervals_below16'],1)

    def test_page_or_session_change_does_not_cross_compare(self):
        result=frame_progress([row(0,10,10),row(20,11,11,page='home'),
                               row(30,12,12),row(40,13,13,session='other')])
        self.assertEqual(result['intervals'],0)

    def test_backwards_counter_and_invalid_stamp_do_not_claim_progress(self):
        result=frame_progress([row(30,10,10),row(20,11,11),row(40,float('nan'),12)])
        self.assertEqual(result['intervals'],0)


if __name__=='__main__':
    unittest.main()
