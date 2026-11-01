import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

from z20_compute.stereo_board import BoardStereo, CAPTURE_MODE, prepare_pair, record_pair


class BoardStereoTests(unittest.TestCase):
    def test_known_disparity_reprojects_to_metres_and_exports_only_finite_points(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);yy,xx=np.mgrid[:180,:160].astype(np.float32)
            # f=100px, baseline=.1m: disparity 10px means depth 1m.
            q=np.array([[1,0,0,-80],[0,1,0,-90],[0,0,0,100],[0,0,10,0]],np.float64)
            np.savez(root/'maps.npz',maps=np.array([xx,yy,xx,yy]),q=q)
            (root/'calibration.json').write_text(json.dumps(dict(format='z20-board-stereo-v1',
                capture_mode=CAPTURE_MODE,image_size=[160,180],units='m',calibration_id='a'*64,
                maps_sha256=hashlib.sha256((root/'maps.npz').read_bytes()).hexdigest())))
            def matcher(left,right,maps,disparities,block_size):
                disparity=np.full(left.shape,10.,np.float32);disparity[:10]=0;return disparity
            engine=BoardStereo(root,matcher=matcher)
            pair=np.zeros((2,180,160),np.uint8)
            result=engine.process(pair,capture_mode=CAPTURE_MODE)
            self.assertAlmostEqual(result.distance_m,1.)
            self.assertEqual(result.valid_points,32*32)
            self.assertFalse(result.valid_mask[:10].any())
            self.assertTrue(np.allclose(result.xyz[90,80],[0,0,1]))
            files=engine.export(root/'clouds',result,sequence=3)
            self.assertEqual(files['points'],170*160)
            content=(root/'clouds'/files['artifact_id']/'cloud.ply').read_bytes()
            header,raw=content.split(b'end_header\n',1)
            self.assertIn(b'comment units metre',header)
            self.assertIn(b'format binary_little_endian 1.0',header)
            points=np.frombuffer(raw,dtype='<f4').reshape(-1,3)
            self.assertEqual(len(points),files['points'])
            self.assertTrue(np.isfinite(points).all())
            self.assertTrue(np.allclose(points[:,2],1.))
            with self.assertRaises(ValueError):engine.process(pair,capture_mode='wrong-mode')
            (root/'maps.npz').write_bytes(b'corrupt')
            with self.assertRaises(ValueError):BoardStereo(root,matcher=matcher)

    def test_calibration_pairs_use_exact_observer_geometry_and_refuse_repeated_frame(self):
        pixels=np.zeros((180,320,3),np.uint8)
        pixels[:,:160]=[255,0,0];pixels[:,160:]=[0,255,0]
        pair=prepare_pair(pixels)
        self.assertEqual(pair.shape,(2,180,160))
        self.assertEqual((int(pair[0,0,0]),int(pair[1,0,0])),(29,150))
        with tempfile.TemporaryDirectory() as directory:
            path=record_pair(directory,pair,sequence=8,captured_ns=123)
            value=json.loads(path.read_text())
            self.assertEqual(value['capture_mode'],CAPTURE_MODE)
            self.assertEqual((Path(directory)/value['pairs'][0]['left']).read_bytes()[:15],b'P5\n160 180\n255\n')
            with self.assertRaises(ValueError):record_pair(directory,pair,sequence=8,captured_ns=123)


if __name__=='__main__':unittest.main()
