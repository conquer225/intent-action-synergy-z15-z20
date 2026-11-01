import unittest
from z20_compute.wireless_only import require_wireless


class WirelessOnlyTests(unittest.TestCase):
    def test_windows_route_with_chinese_adapter_name_uses_utf8(self):
        import json
        from types import SimpleNamespace
        from unittest.mock import patch
        from z20_compute.wireless_only import route_probe
        raw=json.dumps(dict(interface='本地连接* 2',wireless=True),ensure_ascii=False).encode('utf-8')
        def process(*args,**options):
            return SimpleNamespace(stdout=raw.decode(options.get('encoding','gbk')),check_returncode=lambda:None)
        with patch('z20_compute.wireless_only.sys.platform','win32'),patch('z20_compute.wireless_only.subprocess.run',side_effect=process):
            self.assertEqual(route_probe('192.168.137.91')['interface'],'本地连接* 2')

    def test_route_probe_failure_has_a_reconnectable_error(self):
        import subprocess
        def unavailable(_):raise subprocess.CalledProcessError(1,['ip','route'])
        with self.assertRaisesRegex(RuntimeError,'wireless route probe failed'):
            require_wireless('192.168.50.20',probe=unavailable)

    def test_wired_and_implicit_loopback_are_rejected(self):
        with self.assertRaises(RuntimeError):require_wireless('192.168.50.4',probe=lambda _:dict(interface='eth0',wireless=False))
        with self.assertRaises(RuntimeError):require_wireless('127.0.0.1')
        self.assertEqual(require_wireless('127.0.0.1',allow_loopback=True)['kind'],'loopback_test')
        result=require_wireless('192.168.50.4',probe=lambda _:dict(interface='wlan0',wireless=True))
        self.assertEqual(result['interface'],'wlan0')
