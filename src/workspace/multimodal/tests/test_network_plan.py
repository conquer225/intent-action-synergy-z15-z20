import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('station',Path(__file__).resolve().parents[1]/'tools/c3_station.py');station=importlib.util.module_from_spec(spec);spec.loader.exec_module(station)
class NetworkPlanTests(unittest.TestCase):
    def test_config_rejects_newlines_and_keeps_fixed_bridge_network(self):
        row=dict(interface='wlan0',z15_address='192.168.4.3/24',gateway='192.168.4.1',ssid='NaoDun-Control',password='private-test-only')
        self.assertEqual(station.validate(row)['gateway'],'192.168.4.1')
        with self.assertRaises(ValueError):station.validate(dict(row,password='break\nprofile'))
        with self.assertRaises(ValueError):station.validate(dict(row,z15_address='192.168.4.2/24'))
        with self.assertRaises(ValueError):station.validate(dict(row,password=''))
