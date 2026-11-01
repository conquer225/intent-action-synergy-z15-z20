import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"tools"))
from eye_protocol import Decoder, roi_packet, parse_status

STATUS=b"EYE L V1 F1 C7 A0 X087 N00C5 QA4 E0001 DL S0 I5640 R1 !0 K0\r\n"

class ProtocolTests(unittest.TestCase):
    def test_fragmented_text_and_binary(self):
        image=bytes(range(256))*300
        stream=b"noise"+STATUS+b"ZIMG\x40\x01\xf0\x00"+image+STATUS
        for chunk in (1,7,61,4096):
            decoder=Decoder();messages=[]
            for i in range(0,len(stream),chunk):messages+=decoder.feed(stream[i:i+chunk])
            self.assertEqual([m[0] for m in messages],["status","image","status"])
            self.assertEqual(messages[1][1],image)
            self.assertEqual(messages[0][1]["X"],135)
    def test_bounds_and_checksum(self):
        self.assertEqual(roi_packet(120,96,80,40,64),bytes.fromhex("a5 00 78 60 50 28 40 20 5a"))
        for args in [(300,0,32,40,64),(0,220,80,40,64),(0,0,15,40,64),(0,0,80,40,0)]:
            with self.assertRaises(ValueError):roi_packet(*args)
    def test_status(self):
        self.assertEqual(parse_status(STATUS)["D"],"L")
    def test_corrupted_status_recovers(self):
        for broken in (STATUS.replace(b"K0",b"V0"),STATUS.replace(b"DL",b"DZ"),
                       STATUS.replace(b"V1",b"V9"),STATUS.replace(b"X087",b"XFFF"),
                       STATUS.replace(b"EYE L",b"EYE LC")):
            with self.assertRaises(ValueError):parse_status(broken)
            messages=Decoder().feed(broken+STATUS)
            self.assertEqual([m[0] for m in messages],["error","status"])

if __name__=="__main__":unittest.main()
