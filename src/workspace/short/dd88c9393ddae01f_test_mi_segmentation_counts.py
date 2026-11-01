import unittest

from mi_segmentation_count_audit import exact_mean_ba


def row(matrices):
    return {'trials': 140, 'per_seed': [
        {'seed': seed, 'confusion_matrix': matrix}
        for seed, matrix in zip((42, 43, 44), matrices, strict=True)]}


class ExactParticipantCountsTest(unittest.TestCase):
    def test_equal_mean_recall_is_exact_tie(self):
        candidate = row([[[60, 10], [65, 5]], [[53, 17], [53, 17]], [[57, 13], [60, 10]]])
        reference = row([[[66, 4], [69, 1]], [[52, 18], [55, 15]], [[65, 5], [67, 3]]])
        self.assertEqual(exact_mean_ba(candidate), exact_mean_ba(reference))

    def test_seed_identity_is_required(self):
        item = row([[[70, 0], [0, 70]]] * 3)
        item['per_seed'][0]['seed'] = 99
        with self.assertRaises(ValueError):
            exact_mean_ba(item)

    def test_trial_total_is_required(self):
        item = row([[[70, 0], [0, 70]]] * 3)
        item['trials'] = 139
        with self.assertRaises(ValueError):
            exact_mean_ba(item)


if __name__ == '__main__':
    unittest.main()
