import unittest
from unittest.mock import Mock

from soak_service_replay import array_covariance_factory


class ReplayArrayTests(unittest.TestCase):
    def test_explicit_benchmark_array_accepts_current_main_storage_api(self):
        stream=Mock();factory=array_covariance_factory(stream)
        factory(('F3','F4'),storage='deque')
        stream.assert_called_once_with(('F3','F4'),storage='array')

    def test_older_main_call_also_uses_array(self):
        stream=Mock();array_covariance_factory(stream)(('F3','F4'))
        stream.assert_called_once_with(('F3','F4'),storage='array')
