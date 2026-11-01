import unittest
from intent_one.menu import Menu
from intent_one.tasks import TaskController
from test_runtime import Transport
class Media:
    paused=False;picture=None;detail=''
    def __init__(self):self.stopped=0;self.choices=[]
    def labels(self,page):return ['我想喝水','返回','我需要帮助'] if page=='speech' else ['交流表达','多媒体','返回主页']
    def choose(self,page,index,now):self.choices.append((page,index));return 'speech' if page=='more' else page
    def stop(self):self.stopped+=1
    def tick(self):pass
    def pause(self,page):self.paused=not self.paused;return page
    def snapshot(self):return {'detail':'','paused':self.paused}
class MenuMediaTests(unittest.TestCase):
    def test_pre_reading_gaze_cannot_start_a_selection(self):
        m=Menu(TaskController(Transport));m.presented(0)
        m.gaze({'x':.1,'valid':True,'monotonic_ns':1180000000},1.39)
        m.gaze({'x':.1,'valid':True,'monotonic_ns':1400000000},1.60)
        self.assertEqual(m.snapshot(1.6)['hover'],-1)
    def test_eye_home_routes_to_media_without_connecting_an_actuator(self):
        c=TaskController(Transport);m=Menu(c);media=Media();m.media=media
        m.choose(2,0);self.assertEqual(m.page,'more');self.assertIsNone(c.peer)
        m.choose(0,2);self.assertEqual(m.page,'speech');self.assertEqual(m.labels(),['我想喝水','返回','我需要帮助'])
        m.presented(2)
        for n in range(32,52):
            now=n*.1;m.gaze({'x':.1,'valid':True,'monotonic_ns':int(now*1e9)},now)
        self.assertIn(('speech',0),media.choices);self.assertIsNone(c.peer)
    def test_switch_mode_stops_media_and_old_gaze_cannot_select(self):
        m=Menu(TaskController(Transport));media=Media();m.media=media;m.choose(2,0)
        m.switch_mode('emg',1);self.assertGreater(media.stopped,0);m.presented(1)
        for n in range(22,50):m.gaze({'x':.1,'valid':True,'monotonic_ns':int(n*.1*1e9)},n*.1)
        self.assertEqual(m.page,'emg');self.assertEqual(media.choices,[])
