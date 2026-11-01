import unittest
import numpy as np
from vision_demo.signal_core import empty_eeg
from vision_demo.signal_render import SignalPresenter
class SignalRenderTests(unittest.TestCase):
 def test_four_empty_pages_render_hdmi_rgb_and_do_not_invent_data(self):
  p=SignalPresenter();frame=empty_eeg();before=dict(frame)
  for page in ('fatigue','emotion','music','audio'):
   image=p.render(page,frame,{},None,0)
   self.assertEqual(image.shape,(720,1280,3));self.assertEqual(image.dtype,np.uint8)
  self.assertEqual(frame,before)

 def test_wave_plot_keeps_physical_clipping_and_gap_instead_of_joining_missing_points(self):
  from PIL import Image,ImageDraw
  p=SignalPresenter();actual=Image.new('RGB',(130,70),'white');expected=actual.copy()
  p.line_plot(ImageDraw.Draw(actual),[-2,0,2,float('nan'),.5,1],(10,10,110,50),-1,1,'black')
  d=ImageDraw.Draw(expected);d.line([(10,50),(30,30),(50,10)],fill='black',width=2);d.line([(90,20),(110,10)],fill='black',width=2)
  self.assertEqual(actual.tobytes(),expected.tobytes())
