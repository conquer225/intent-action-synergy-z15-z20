import struct,tempfile,unittest
from pathlib import Path
import numpy as np
from z20_compute.stereo_live import StereoUIO


class MainCameraTests(unittest.TestCase):
    def test_single_left_copy_ignores_right_pairing_but_retains_write_fence(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);device=root/'uio0'
            with device.open('wb') as stream:stream.truncate(4096+8294400)
            for index,address,size in ((0,0x43c20000,4096),(1,0x01000000,8294400)):
                info=root/('map'+str(index));info.mkdir()
                for name,value in (('addr',address),('size',size),('offset',0)):(info/name).write_text(hex(value))
            words={0:0x5a325643,4:1,8:7,0xc:142857132,0x40:0x01000000,
                0x44:2764800,0x48:3840,0x4c:720,0x50:1920,
                0x10:0x103,0x14:101,0x18:100,0x1c:4,0x20:98,0x24:97,
                0x28:2_000_000,0x30:2_000_000,0x38:1_000_000}
            with device.open('r+b') as stream:
                for offset,value in words.items():stream.seek(offset);stream.write(struct.pack('<I',value))
                stream.seek(4096);stream.write(b'\x01\x02\x03')
            with StereoUIO(device,root,sample_step=(4,4),camera_index=0) as capture:
                frame=capture.latest()
                self.assertEqual(frame.pixels.shape,(180,160,3))
                self.assertEqual(frame.sequence,100)
                np.testing.assert_array_equal(frame.pixels[0,0],[1,2,3])
                self.assertFalse(frame.pixels.flags.writeable)
                self.assertIsNone(capture.latest())
            with StereoUIO(device,root,sample_step=(4,4),camera_index=0) as capture:
                original=capture.reader.copy_frame
                def lapped(slot):
                    result=original(slot)
                    with device.open('r+b') as stream:stream.seek(0x14);stream.write(struct.pack('<I',104))
                    return result
                capture.reader.copy_frame=lapped
                self.assertIsNone(capture.latest())

    def test_main_rgb_conversion_preserves_original_aspect_and_channels(self):
        from z20_compute.person_dog_camera_scene import main_input_rgb,photo_input_rgb
        pixels=np.zeros((180,160,3),np.uint8);pixels[9,7]=[11,22,33]
        frame=main_input_rgb(pixels)
        self.assertEqual(frame.shape,(360,320,3))
        np.testing.assert_array_equal(frame[18:20,14:16],np.tile([33,22,11],(2,2,1)))
        paired=np.concatenate((pixels,np.zeros_like(pixels)),axis=1)
        np.testing.assert_array_equal(frame,photo_input_rgb(paired))
