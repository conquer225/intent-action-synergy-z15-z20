import io
import unittest
import cv2
import numpy as np

from z20_compute.visual_wire import read_json, write_json, read_frame, write_frame, decode_jpeg


class WireTests(unittest.TestCase):
    def test_jpeg_roundtrip_exact_envelope_and_rgb_order(self):
        rgb=np.zeros((90,160,3),np.uint8);rgb[:]=(230,40,15)
        ok,jpeg=cv2.imencode('.jpg',rgb[...,::-1]);self.assertTrue(ok)
        stream=io.BytesIO()
        write_frame(stream,'a'*32,4,7,jpeg.tobytes());stream.seek(0)
        meta,payload=read_frame(stream)
        self.assertEqual((meta['epoch'],meta['sequence']),(4,7))
        image=decode_jpeg(payload)
        self.assertEqual(image.shape,(720,1280,3))
        self.assertLess(np.max(np.abs(image[0,0].astype(int)-rgb[0,0])),5)

    def test_bounds_nan_and_truncated_payload(self):
        for raw in (b'{"x":NaN}\n', b'x'*65537, b'{"ok":true}'):
            with self.assertRaises((ValueError,EOFError)):read_json(io.BytesIO(raw))
        stream=io.BytesIO();write_json(stream,dict(session='a'*32,epoch=0,sequence=1,length=1024*1024+1));stream.seek(0)
        with self.assertRaises(ValueError):read_frame(stream)
        with self.assertRaises(ValueError):decode_jpeg(b'not jpeg')
