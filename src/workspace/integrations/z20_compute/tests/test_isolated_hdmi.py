import unittest

from z20_compute.isolated_hdmi import OverlayDisplay,FRAME_BYTES,DISPLAY_BASE


class Registers:
    def __init__(self):self.values={0x20000:0,0x20004:1};self.writes=[]
    def read(self,offset):return self.values.get(offset,0)
    def write(self,offset,value):
        self.writes.append((offset,value))
        self.values[offset]=value
        if offset==0x20000 and value==4:self.values[offset]=0
        if offset==0x20000 and value&1:self.values[0x20004]=0x10000
        if offset==0x20004:self.values[offset]=0x10000
        if offset==0x20028:self.values[offset]=(value&31)<<16 | (value&31)


class IsolatedHDMITests(unittest.TestCase):
    def test_overlay_updates_only_separate_display_memory_and_mm2s(self):
        registers,vtc=Registers(),Registers()
        pixels=bytearray(3*FRAME_BYTES)
        display=OverlayDisplay(registers,vtc,pixels)
        frame=bytes([37])*FRAME_BYTES
        display.show(frame)
        display.show(bytes([93])*FRAME_BYTES)
        self.assertFalse(any(offset<0x20000 for offset,_ in registers.writes))
        self.assertEqual([registers.values[0x2005c+4*i] for i in range(3)],
                         [DISPLAY_BASE+i*FRAME_BYTES for i in range(3)])
        self.assertEqual(pixels[FRAME_BYTES:2*FRAME_BYTES],bytes([93])*FRAME_BYTES)
        self.assertEqual(display.readback(), bytes([93])*FRAME_BYTES)

    def test_incorrect_frame_size_is_rejected_before_mmio(self):
        registers=Registers()
        display=OverlayDisplay(registers,Registers(),bytearray(3*FRAME_BYTES))
        with self.assertRaises(ValueError):display.show(b'bad')
        self.assertEqual(registers.writes,[])
