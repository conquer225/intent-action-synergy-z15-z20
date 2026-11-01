import unittest

from mi_cued_acceptance import cue_counts


class AccountingTests(unittest.TestCase):
    def test_bench_eof_has_one_incomplete_target_not_an_extra_rest(self):
        self.assertEqual(cue_counts(39000),dict(trials=20,rest=6,complete=13,incomplete=1))

    def test_complete_and_incomplete_boundary(self):
        self.assertEqual(cue_counts(1375),dict(trials=1,rest=0,complete=1,incomplete=0))
        self.assertEqual(cue_counts(1374),dict(trials=1,rest=0,complete=0,incomplete=1))


if __name__=='__main__':
    unittest.main()
