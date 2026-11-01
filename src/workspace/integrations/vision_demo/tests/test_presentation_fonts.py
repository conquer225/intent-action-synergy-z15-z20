import unittest
from PIL import Image,ImageDraw
from vision_demo.presentation import Presenter

class PresentationFontTests(unittest.TestCase):
 def test_math_and_greek_labels_use_available_latin_glyphs(self):
  p=Presenter();actual=Image.new('RGB',(400,80),'white');expected=actual.copy()
  text='αθδβγ±μ−'
  p.text(ImageDraw.Draw(actual),(0,0),text,p.body,'black')
  latin=p.latin[p.body.size];offset=p.body.getmetrics()[0]-latin.getmetrics()[0]
  ImageDraw.Draw(expected).text((0,offset),text,font=latin,fill='black')
  self.assertEqual(actual.tobytes(),expected.tobytes())
