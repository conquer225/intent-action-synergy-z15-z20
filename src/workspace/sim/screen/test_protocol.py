import sys
import unittest
from functools import reduce
from operator import xor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"tools"))
from screen_protocol import Decoder, eye_packet, parse_status

STATUS=b"SCR L V1 F3 M4 C7 P00 T0 H0 G0 A1 X70 Y71 E0001 DL S0 I5640 R1 !0\r\n"


class ProtocolTests(unittest.TestCase):
    def test_packet(self):
        p=eye_packet(1,352,200,64,32,70,140)
        self.assertEqual(len(p),12)
        self.assertEqual(p[1:10],bytes((1,1,96,0,200,64,32,70,140)))
        self.assertEqual(p[10],reduce(xor,p[1:10]))
        for args in ((2,0,0,64,32,70,140),(0,620,0,64,32,70,140),(0,0,0,20,32,70,140),(0,0,0,64,32,130,140)):
            with self.assertRaises(ValueError):eye_packet(*args)

    def test_fragmented_stream(self):
        p=eye_packet(0,224,200,64,32,70,140)
        pixels=bytes(range(256))*300
        stream=STATUS+b"RCFG"+p[1:11]+b"ZIMG\x40\x01\xf0\x00"+pixels+STATUS
        for chunk in (1,7,67,4096):
            d=Decoder();messages=[]
            for i in range(0,len(stream),chunk):messages+=d.feed(stream[i:i+chunk])
            self.assertEqual([m[0] for m in messages],["status","ack","image","status"])
            self.assertEqual(messages[2][1],pixels)
            self.assertEqual(messages[1][1],p[1:10])

    def test_corruption_and_old_firmware(self):
        for broken in (STATUS.replace(b"F3",b"F8"),STATUS.replace(b"M4",b"M9"),STATUS.replace(b"DL",b"DZ"),STATUS.replace(b"!0",b"V0")):
            with self.assertRaises(ValueError):parse_status(broken)
            self.assertEqual([m[0] for m in Decoder().feed(broken+STATUS)],["error","status"])
        self.assertIn("旧版",Decoder().feed(b"EYE I anything\r\n")[0][1])

if __name__=="__main__":unittest.main()
