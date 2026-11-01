import copy
import unittest

from mi_model_comparison_audit import primary_reference_key


class ReportingReferenceTests(unittest.TestCase):
    def test_locked_descriptive_reference_resolves_without_mutation(self):
        protocol = {'methods': ['B0_CSP_LDA', 'B1_EA_CSP_ERD_LDA'],
                    'primary_reference': 'B1_EA_CSP_ERD_LDA rerun with same26 fit people'}
        original = copy.deepcopy(protocol)
        self.assertEqual(primary_reference_key(protocol), 'B1_EA_CSP_ERD_LDA')
        self.assertEqual(protocol, original)

    def test_exact_identifier(self):
        self.assertEqual(primary_reference_key({'methods': ['B1'], 'primary_reference': 'B1'}), 'B1')

    def test_unknown_reference_is_not_guessed(self):
        with self.assertRaises(ValueError):
            primary_reference_key({'methods': ['B1'], 'primary_reference': 'B1_unknown'})

    def test_ambiguous_description_is_rejected(self):
        with self.assertRaises(ValueError):
            primary_reference_key({'methods': ['B1', 'B1 extra'], 'primary_reference': 'B1 extra description'})


if __name__ == '__main__':
    unittest.main()
