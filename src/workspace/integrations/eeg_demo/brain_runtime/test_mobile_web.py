import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from unittest.mock import patch

import guardianloop_web as web


class MobileWebTests(unittest.TestCase):
    def test_mobile_routes_use_existing_server_without_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(web, 'system_status', return_value={}):
                server = ThreadingHTTPServer(('127.0.0.1', 0),
                    web.make_handler(root/'status', root/'telemetry', 20))
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    for route, content_type, expected in (
                        ('/mobile', 'text/html', '手机监控'),
                        ('/mobile/', 'text/html', '手机监控'),
                        ('/mobile.js', 'text/javascript', 'pollMobile'),
                        ('/', 'text/html', '/mobile')):
                        with urlopen('http://127.0.0.1:%s%s' % (server.server_port, route)) as response:
                            self.assertEqual(response.status, 200)
                            self.assertIn(content_type, response.headers['Content-Type'])
                            self.assertEqual(response.headers['Cache-Control'], 'no-store')
                            self.assertIn(expected, response.read().decode('utf-8'))
                    self.assertFalse((root/'status').exists())
                    self.assertFalse((root/'telemetry').exists())
                finally:
                    server.shutdown()
                    server.server_close()
                    worker.join()


if __name__ == '__main__':
    unittest.main()
