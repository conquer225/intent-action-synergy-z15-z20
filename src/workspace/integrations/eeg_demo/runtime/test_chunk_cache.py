import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

import numpy as np
import chunk_cache as cache


class Codec:
    def compress(self,frame):return zlib.compress(frame.tobytes())
    def decompress(self,payload,frame):
        data=zlib.decompress(payload)
        if len(data)!=frame.size:raise ValueError('bad size')
        frame[:]=np.frombuffer(data,dtype=np.uint8)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.patch=patch.object(cache,'FRAME_BYTES',128);self.patch.start()
        self.addCleanup(self.patch.stop);self.addCleanup(self.tmp.cleanup)

    def make(self,counts=(16,16,5)):
        chunks=[];values=[]
        for i,n in enumerate(counts):
            path=self.root/('chunk_%06d.bin'%i)
            with path.open('wb') as out:
                for j in range(n):
                    frame=np.full(128,len(values)%256,dtype=np.uint8);values.append(frame.copy())
                    cache.write_frame(out,frame,Codec())
            chunks.append({'file':path.name,'frames':n,'bytes':path.stat().st_size})
        meta={'format':'gl-yuv420-lz4-v1','fps':20,'width':1280,'height':720,
              'frames':sum(counts),'chunks':chunks}
        (self.root/'manifest.json').write_text(json.dumps(meta))
        return values,meta

    def test_blocks_preserve_order_and_fixed_two_slots(self):
        expected,_=self.make();source=cache.BoundedChunks(self.root,Codec());seen=[]
        try:
            self.assertEqual(source.allocated_bytes,2*16*128)
            while True:
                block=source.acquire(timeout=2)
                if block is None:break
                slot,n=block;seen.extend(frame.copy() for frame in source.slots[slot][:n]);source.release(slot)
            self.assertEqual(len(seen),37)
            self.assertTrue(all(np.array_equal(a,b) for a,b in zip(expected,seen)))
        finally:source.close()

    def test_corruption_is_not_published_as_valid_frames(self):
        self.make((2,));path=self.root/'chunk_000000.bin';data=bytearray(path.read_bytes());data[-1]^=1;path.write_bytes(data)
        source=cache.BoundedChunks(self.root,Codec())
        try:
            with self.assertRaises(ValueError):source.acquire(timeout=1)
        finally:source.close()

    def test_truncated_payload(self):
        out=io.BytesIO();cache.write_frame(out,np.zeros(128,dtype=np.uint8),Codec())
        with self.assertRaises(ValueError):cache.read_frame(io.BytesIO(out.getvalue()[:-1]),np.empty(128,dtype=np.uint8),Codec())

    def test_manifest_rejects_path_escape_and_frame_overallocation(self):
        _,meta=self.make((1,));meta['chunks'][0]['file']='../foreign.bin'
        (self.root/'manifest.json').write_text(json.dumps(meta))
        with self.assertRaises(ValueError):cache.manifest(self.root)
        meta['chunks'][0]['file']='chunk_000000.bin';meta['chunks'][0]['frames']=17
        (self.root/'manifest.json').write_text(json.dumps(meta))
        with self.assertRaises(ValueError):cache.manifest(self.root)

    def test_cancel_while_both_slots_are_occupied(self):
        self.make((16,16,16));source=cache.BoundedChunks(self.root,Codec())
        source.close();self.assertFalse(source.thread.is_alive())

    def test_finite_clip_loops_in_same_two_slots_without_eof_reallocation(self):
        expected,_=self.make((3,));source=cache.BoundedChunks(self.root,Codec(),loop=True)
        slots=tuple(id(slot) for slot in source.slots)
        try:
            for _ in range(4):
                index,n=source.acquire(timeout=2)
                self.assertEqual(n,3)
                self.assertTrue(all(np.array_equal(a,b) for a,b in zip(expected,source.slots[index][:n])))
                source.release(index)
            self.assertEqual(tuple(id(slot) for slot in source.slots),slots)
            self.assertFalse(source.complete)
        finally:source.close()

    def test_raw_incompressible_frame(self):
        frame=np.arange(128,dtype=np.uint8);out=io.BytesIO();cache.write_frame(out,frame,Codec())
        recovered=np.empty_like(frame);out.seek(0);cache.read_frame(out,recovered,Codec())
        self.assertTrue(np.array_equal(frame,recovered))

    def test_delta_requires_local_reference_and_roundtrips(self):
        before=np.arange(128,dtype=np.uint8);after=before.copy();after[50]^=7
        out=io.BytesIO();cache.write_frame(out,after,Codec(),before)
        encoded=out.getvalue();recovered=np.empty_like(after)
        with self.assertRaises(ValueError):cache.read_frame(io.BytesIO(encoded),recovered,Codec())
        cache.read_frame(io.BytesIO(encoded),recovered,Codec(),before)
        self.assertTrue(np.array_equal(after,recovered))
        self.assertTrue(np.array_equal(before,np.arange(128,dtype=np.uint8)))

    def test_compact_cache_dimensions_and_frame_allocation_are_bounded(self):
        _,meta=self.make((1,))
        meta.update(format='gl-bgr24-lz4-v1',width=640,height=360)
        (self.root/'manifest.json').write_text(json.dumps(meta))
        self.assertEqual(cache.manifest(self.root)['frame_bytes'],640*360*3)
        meta.update(width=384,height=216)
        (self.root/'manifest.json').write_text(json.dumps(meta))
        self.assertEqual(cache.manifest(self.root)['frame_bytes'],384*216*3)
        meta['format']='gl-yuv420-lz4-v1'
        (self.root/'manifest.json').write_text(json.dumps(meta))
        with self.assertRaises(ValueError):cache.manifest(self.root)
        meta.update(format='gl-bgr24-lz4-v1',width=4096,height=2160)
        (self.root/'manifest.json').write_text(json.dumps(meta))
        with self.assertRaises(ValueError):cache.manifest(self.root)


if __name__=='__main__':unittest.main()
