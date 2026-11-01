from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import Image
from prepare_display_asset import fit_geometry
from prepare_sd_portrait import fit_sd,jpeg_avi


class PortraitTests(unittest.TestCase):
    def test_contain_landscape_portrait_and_rotation_without_stretch(self):
        self.assertEqual(fit_geometry(1080,1920,1,0),(288,512,0,0))
        self.assertEqual(fit_geometry(1920,1080,1,90),(288,512,0,0))
        self.assertEqual(fit_geometry(1920,1080,1,0),(288,162,0,175))
        with self.assertRaises(ValueError):fit_geometry(10,10,1,45)

    def test_specific_sd_crop_requires_black_padding(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'frame.jpg';a=np.zeros((360,640,3),dtype=np.uint8);a[:,218:420]=[200,80,20]
            Image.fromarray(a).save(p,quality=95)
            fitted=fit_sd(p);self.assertEqual(fitted.size,(288,512))
            self.assertGreater(np.asarray(fitted)[:,:,0].mean(),190)
            a[:,:214]=255;Image.fromarray(a).save(p)
            with self.assertRaises(ValueError):fit_sd(p)

    def test_mjpeg_intermediate_is_bounded_and_exclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'a.avi';jpeg_avi(p,[b'123',b'abcdef'],10)
            b=p.read_bytes();self.assertEqual(b[:4],b'RIFF');self.assertEqual(b[8:12],b'AVI ')
            self.assertIn(b'MJPG',b)
            with self.assertRaises(FileExistsError):jpeg_avi(p,[b'a'],10)


if __name__=='__main__':unittest.main()
