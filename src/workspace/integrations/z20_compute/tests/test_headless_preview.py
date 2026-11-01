import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import numpy as np
from PIL import Image


class PreviewTests(unittest.TestCase):
    def test_png_preserves_rgb_pixels_and_http_refuses_expired_preview(self):
        from z20_compute.headless_preview import publish_frame, preview_fresh
        from z20_compute.headless_server import StatusHTTP
        frame = np.zeros((720, 1280, 3), np.uint8)
        frame[:, :600] = [255, 4, 12]; frame[:, 600:] = [3, 9, 250]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'frame.png'
            metadata = publish_frame(path, frame, now=10.)
            np.testing.assert_array_equal(np.asarray(Image.open(io.BytesIO(path.read_bytes()))), frame)
            self.assertEqual(metadata['rgb_sha256'], hashlib.sha256(frame.tobytes()).hexdigest())
            self.assertTrue(preview_fresh(path, now=11.))
            self.assertFalse(preview_fresh(path, now=13.))
            server = StatusHTTP(('127.0.0.1', 0), lambda: {'results': {}}, preview=path)
            thread = threading.Thread(target=server.serve_forever); thread.start()
            try:
                base = 'http://127.0.0.1:%d' % server.server_port
                self.assertEqual(json.load(urllib.request.urlopen(base+'/status.json')), {'results': {}})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(base+'/frame.png')
                self.assertEqual(caught.exception.code, 404)
                publish_frame(path, frame)
                self.assertEqual(urllib.request.urlopen(base+'/frame.png').read(), path.read_bytes())
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(base+'/../../etc/passwd')
            finally:
                server.shutdown(); thread.join(); server.server_close()


if __name__ == '__main__': unittest.main()
