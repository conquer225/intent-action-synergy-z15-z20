"""Linux pipe-only tests of acquisition timing; no serial or PL access."""
import os
import unittest


@unittest.skipUnless(os.name=='posix','Reader uses Linux fork')
class ReaderTimingTests(unittest.TestCase):
    def test_timestamped_packets_and_idle_timeout(self):
        from cyton_guardianloop import packets
        r,w=os.pipe()
        ticks=[]
        frames=b''.join(bytes([0xA0,i])+bytes(30)+bytes([0xC0]) for i in range(3))
        os.write(w,frames)
        reader=packets(r,.6,with_timing=True,on_idle=ticks.append)
        try:
            values=[next(reader) for _ in range(3)]
            self.assertEqual([v[0][1] for v in values],[0,1,2])
            self.assertTrue(all(len(v)==3 and v[1]==0 and v[2]>0 for v in values))
            self.assertTrue(all(v[2]==values[0][2] for v in values))
            with self.assertRaises(TimeoutError):next(reader)
            self.assertGreater(len(ticks),0)
        finally:
            reader.close();os.close(r);os.close(w)

    def test_default_api_retains_two_fields(self):
        from cyton_guardianloop import packets
        r,w=os.pipe();os.write(w,(bytes([0xA0,1])+bytes(30)+bytes([0xC0]))*2)
        reader=packets(r,1)
        try:self.assertEqual(len(next(reader)),2)
        finally:reader.close();os.close(r);os.close(w)


if __name__=='__main__':unittest.main()
