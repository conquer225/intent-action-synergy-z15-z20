import tempfile
from pathlib import Path
import unittest
from PIL import Image
import numpy as np
from vision_demo.sources import PgmSource


class RealFrameAdmissionTests(unittest.TestCase):
    def test_new_frame_only_and_freshness_uses_receipt_not_old_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            source=PgmSource(Path(folder),generation=3)
            path=Path(folder)/'frame.pgm'
            Image.fromarray(np.full((24,32),40,np.uint8)).save(path)
            frame=source.read(10.0)
            self.assertEqual(frame.source,'tobii')
            self.assertEqual(frame.generation,3)
            self.assertIsNone(source.read(10.2))
            source.close()

    def test_does_not_reuse_files_present_when_source_was_opened(self):
        with tempfile.TemporaryDirectory() as folder:
            Image.fromarray(np.zeros((24,32),np.uint8)).save(Path(folder)/'old.pgm')
            source=PgmSource(Path(folder),generation=4)
            self.assertIsNone(source.read(12.0))


if __name__=='__main__':unittest.main()
