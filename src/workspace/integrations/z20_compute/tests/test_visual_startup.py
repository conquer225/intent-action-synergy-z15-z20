import sys,unittest
from unittest.mock import patch
from z20_compute import headless_server


class StartupTests(unittest.TestCase):
    def test_startup_failure_releases_npu_resources(self):
        closed=[]
        class Resource:
            def __init__(self,name):self.name=name
            def close(self):closed.append(self.name)
        with patch.object(sys,'argv',['headless_server','--models','missing-model-dir']), \
             patch.object(headless_server,'open_npu',return_value=tuple(Resource(n) for n in ('npu','pool','registers'))), \
             patch.object(headless_server,'load_enabled_models',side_effect=ValueError('model metadata corrupt')):
            with self.assertRaisesRegex(ValueError,'model metadata corrupt'):headless_server.main()
        self.assertEqual(closed,['npu','pool','registers'])
