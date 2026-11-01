import json
import tempfile
import unittest
import struct
import os
from unittest.mock import patch
from pathlib import Path
import numpy as np
from z20_compute.video import FrameSnapshot
from z20_compute.stereo_run import record_pair, main, save_depth_snapshot
from z20_compute.stereo import Calibration, DepthResult


class StereoRunTests(unittest.TestCase):
    def test_record_entry_accepts_independent_ring_slots_without_changing_capture_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);device=root/'uio0'
            with device.open('wb') as f: f.truncate(4096+8294400)
            for index,address,size in [(0,0x43c20000,4096),(1,0x01000000,8294400)]:
                info=root/('map'+str(index));info.mkdir()
                for name,value in [('addr',address),('size',size),('offset',0)]:
                    (info/name).write_text(hex(value))
            words={0:0x5a325643,4:1,0xc:142857132,0x40:0x01000000,0x44:2764800,
                   0x48:3840,0x4c:720,0x50:1920,0x10:0x803,0x14:8,0x18:7,
                   0x1c:0x603,0x20:8,0x24:7}
            with device.open('r+b') as f:
                for offset,value in words.items():f.seek(offset);f.write(struct.pack('<I',value))
            main(['record','--device',str(device),'--maps',str(root),'--pixel-order','BGR',
                  '--output',str(root/'output'),'--independent-slots','--count','1','--seconds','.5'])
            record=json.loads((root/'output/pairs.json').read_text())
            self.assertEqual(record['pairs'][0]['sequence'],7)
            self.assertEqual(record['capture_mode'],'z20-sbs-640x720-BGR-gray-320x240')

    def test_depth_snapshot_can_feed_existing_pc_fusion_without_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            result=DepthResult(1.,np.array([[8.,0]],np.float32),
                np.array([[[0,0,1],[0,0,0]]],np.float32),np.array([[True,False]]))
            save_depth_snapshot(root,result,sequence=7,captured_ns=1234,capture_mode='fixture')
            with np.load(root/'depth.npz',allow_pickle=False) as data:
                np.testing.assert_array_equal(data['xyz'][data['valid_mask']],[[0,0,1]])
            self.assertIn('element vertex 1',(root/'cloud.ply').read_text())
            value=json.loads((root/'snapshot.json').read_text())
            self.assertEqual((value['sequence'],value['units'],value['capture_mode']),(7,'m','fixture'))
            import hashlib
            for name,digest in value['files'].items():
                self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest)

    def test_missing_frames_publish_waiting_once_and_clear_distance_on_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);device=root/'uio0'
            with device.open('wb') as f:f.truncate(4096+8294400)
            for index,address,size in [(0,0x43c20000,4096),(1,0x01000000,8294400)]:
                info=root/('map'+str(index));info.mkdir()
                for name,value in [('addr',address),('size',size),('offset',0)]:
                    (info/name).write_text(hex(value))
            with device.open('r+b') as f:
                for offset,value in {0:0x5a325643,4:1,0xc:142857132,0x40:0x01000000,
                        0x44:2764800,0x48:3840,0x4c:720,0x50:1920}.items():
                    f.seek(offset);f.write(struct.pack('<I',value))
            k=[[100,0,160],[0,100,120],[0,0,1]]
            calibration=root/'calibration.json'
            Calibration((320,240),k,[0]*5,k,[0]*5,np.eye(3),[-.1,0,0],
                        'z20-sbs-640x720-BGR-gray-320x240').save(calibration)
            published=[];replace=os.replace
            def observe(source,destination):
                replace(source,destination)
                published.append(json.loads(Path(destination).read_text()))
            with patch('z20_compute.stereo_run.os.replace',side_effect=observe):
                main(['depth','--device',str(device),'--maps',str(root),'--pixel-order','BGR',
                      '--output',str(root/'output'),'--calibration',str(calibration),'--seconds','.09'])
            self.assertEqual([r['state'] for r in published],['waiting_for_fresh_pair','stopped'])
            self.assertTrue(all(r['distance_m'] is None and not r['valid'] for r in published))

    def test_saved_pair_and_manifest_share_capture_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            pixels = np.zeros((720, 1280, 3), np.uint8)
            pixels[:, :640, 2] = 255
            pixels.flags.writeable = False
            manifest = record_pair(directory, FrameSnapshot(15, 1234, pixels), pixel_order='BGR')
            value = json.loads(Path(manifest).read_text())
            self.assertEqual(value['capture_mode'], 'z20-sbs-640x720-BGR-gray-320x240')
            self.assertEqual(value['pairs'][0]['sequence'], 15)
            import cv2
            image = cv2.imread(str(Path(directory)/value['pairs'][0]['left']), 0)
            self.assertEqual(image.shape, (240, 320))
            self.assertEqual(int(image[0,0]), 76)
            record_pair(directory, FrameSnapshot(16, 2234, pixels), pixel_order='BGR')
            self.assertEqual(len(json.loads(Path(manifest).read_text())['pairs']), 2)


if __name__ == '__main__': unittest.main()
