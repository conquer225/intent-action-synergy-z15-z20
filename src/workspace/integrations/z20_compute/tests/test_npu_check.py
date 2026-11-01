import unittest
from z20_compute.npu_check import check_vectors


class NpuCheckTests(unittest.TestCase):
    def test_board_vectors_cover_all_four_models_with_independent_expected_scores(self):
        vectors = check_vectors()
        self.assertEqual([len(v) for _, v, _ in vectors], [2, 20, 40, 180, 1024])
        self.assertEqual([list(expected) for _, _, expected in vectors],
                         [[3, 125, -3], [-59, 247, -9], [-91, 247, 1],
                          [-88, 247, 0], [-11, 121, -5]])
        for model, values, expected in vectors:
            self.assertEqual(model.infer(values).tolist(), list(expected))


if __name__ == '__main__': unittest.main()
