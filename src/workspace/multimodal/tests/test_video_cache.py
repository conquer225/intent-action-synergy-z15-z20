import json,struct,tempfile,time,unittest,zlib
from pathlib import Path
from intent_one.video_cache import CacheVideo
from chunk_cache import BoundedChunks
class RawCodec:
    def decompress(self,payload,frame):raise AssertionError('raw fixture must not call LZ4')
class CacheVideoTests(unittest.TestCase):
    def test_existing_portrait_format_plays_without_second_display_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);payload=bytes([11,22,33])*(288*512)
            packet=struct.pack('<4sIII',b'GLY1',0,len(payload),zlib.crc32(payload)&0xffffffff)+payload
            (root/'chunk_000000.bin').write_bytes(packet*2)
            (root/'manifest.json').write_text(json.dumps(dict(format='gl-bgr24-lz4-v1',width=288,height=512,fps=10,frames=2,
                chunks=[dict(file='chunk_000000.bin',frames=2,bytes=len(packet)*2)])),encoding='utf8')
            player=CacheVideo(source_factory=lambda path,**options:BoundedChunks(path,codec=RawCodec(),**options),clock=lambda:0)
            try:
                self.assertTrue(player.start(root));frame=None
                for _ in range(50):
                    frame,state,error=player.poll()
                    if frame:break
                    time.sleep(.002)
                self.assertIsNotNone(frame);self.assertEqual(frame[1].size,(288,512));self.assertEqual(frame[1].getpixel((0,0)),(33,22,11))
                self.assertEqual(player.source.allocated_bytes,16*288*512*3*2)
            finally:player.close()
            self.assertEqual(player.status,'idle')
if __name__=='__main__':unittest.main()
