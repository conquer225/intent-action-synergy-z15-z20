import tempfile,time,unittest
from pathlib import Path
from PIL import Image
import numpy as np
from vision_demo.tobii_owner import TobiiImages

class SharedOwnerTests(unittest.TestCase):
 def test_source_follows_replaced_eye_owner_without_opening_second_usb_owner(self):
  with tempfile.TemporaryDirectory() as root:
   first=Path(root)/'first';second=Path(root)/'second';first.mkdir();second.mkdir()
   current=[first];source=TobiiImages(7,shared_directory=lambda:current[0])
   try:
    Image.fromarray(np.full((24,32),20,np.uint8)).save(first/'frame.pgm')
    self.assertEqual(int(source.read(time.monotonic()).rgb[0,0,0]),20)
    current[0]=second
    self.assertIsNone(source.read(time.monotonic()))
    Image.fromarray(np.full((24,32),70,np.uint8)).save(second/'frame.pgm')
    frame=source.read(time.monotonic());self.assertEqual(int(frame.rgb[0,0,0]),70)
    self.assertEqual(frame.generation,7);self.assertGreater(frame.sequence,1)
    self.assertIsNone(source.process)
   finally:source.close()
