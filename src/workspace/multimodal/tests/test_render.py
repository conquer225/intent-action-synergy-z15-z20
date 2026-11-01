import unittest
from PIL import Image
from intent_one.render import Renderer
class RenderTests(unittest.TestCase):
    def test_video_navigation_labels_are_not_covered_by_the_frame(self):
        state=dict(page='operate',menu_page='video_nav',labels=['上一条','返回观看','下一条'],origin='simulation',interaction_mode='eye')
        image=Image.new('RGB',(288,512),(255,0,0));renderer=Renderer()
        self.assertEqual(renderer.render(state,image).tobytes(),renderer.render(state).tobytes())
    def test_cached_page_does_not_retain_old_video_or_selection(self):
        renderer=Renderer();state=dict(page='operate',menu_page='video',labels=['翻动视频','','评价'],origin='simulation',interaction_mode='eye')
        red=Image.new('RGB',(288,512),(255,0,0));blue=Image.new('RGB',(288,512),(0,0,255))
        first=renderer.render(state,red);second=renderer.render(state,blue)
        self.assertEqual(first.getpixel((640,364)),(255,0,0));self.assertEqual(second.getpixel((640,364)),(0,0,255))
        self.assertNotEqual(renderer.render(dict(state,hover=0,progress=.5),blue).getpixel((100,483)),second.getpixel((100,483)))
if __name__=='__main__':unittest.main()
