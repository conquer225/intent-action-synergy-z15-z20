import unittest
from intent_one.controls import PlButtons
class Mmio:
    def __init__(self,value=3):self.value=value;self.writes=[]
    def read(self,address):return self.value
    def write(self,address,value):self.writes.append((address,value))
class ControlsTests(unittest.TestCase):
    def test_debounce_held_startup_release_and_stop_priority(self):
        io=Mmio(2);buttons=PlButtons(io)
        self.assertEqual(buttons.poll(0),[])
        self.assertEqual(buttons.poll(.2),[]) # KEY0 held at boot.
        io.value=3;buttons.poll(.21);buttons.poll(.27)
        io.value=2;buttons.poll(.3);self.assertEqual(buttons.poll(.32),[])
        self.assertEqual(buttons.poll(.36),['mode_next'])
        self.assertEqual(buttons.poll(2),[])
        io.value=3;buttons.poll(2.1);buttons.poll(2.16)
        io.value=0;buttons.poll(3);self.assertEqual(buttons.poll(3.06),['stop'])
        self.assertEqual(io.writes,[(4,3)])
if __name__=='__main__':unittest.main()
