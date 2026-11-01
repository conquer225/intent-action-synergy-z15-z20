"""Head transform must not subtract eye motion reported by a moving cascade box.

Generated images and injected detector outputs isolate a geometry bug. They do
not establish that a user's actual Haar boxes moved this way, or human accuracy.
"""
import ctypes as C
import time
import unittest
from test_pc_gaze import GazeEngine,Loc,Box,Roi,cv2,np


class RoiMotion(unittest.TestCase):
    def setUp(self):self.e=GazeEngine()
    def tearDown(self):self.e.close()

    def observe(self,gaze=0,box_motion=0,dx=0,dy=0,scale=1.,n=1):
        base=np.full((220,360,3),160,np.uint8)
        for x in (110,220):cv2.circle(base,(x+gaze,104),7,(5,5,5),-1)
        tx=160*(1-scale)+dx;ty=110*(1-scale)+dy
        frame=cv2.warpAffine(base,np.float32([[scale,0,tx],[0,scale,ty]]),(360,220),
                             flags=cv2.INTER_NEAREST,borderValue=(160,160,160))
        def box(x,y,w,h):return [round(x*scale+tx),round(y*scale+ty),round(w*scale),round(h*scale)]
        loc=Loc(Box(*box(50,40,230,150),1),Roi(*box(75+box_motion,80,70,48),24,80),
                Roi(*box(185+box_motion,80,70,48),24,80),1,1,2)
        for _ in range(n):
            self.e.lib.pc_gaze_step(self.e.context,frame.ctypes.data,frame.strides[0],360,220,C.byref(loc),100,20)
        return self.e.state()

    def calibrate(self):
        self.observe(n=2);self.e.last_sample=time.monotonic()
        self.assertTrue(self.e.calibrate())
        for gaze in (-12,0,12):s=self.observe(gaze,gaze,n=36)
        self.assertEqual(s['cal_mask'],7, f"References collapsed: {s['cal_l_left']}/{s['cal_l_center']}/{s['cal_l_right']}")
        return s

    def test_eye_boxes_following_pupils_do_not_collapse_calibration(self):
        s=self.calibrate()
        self.assertGreater(s['cal_l_center']-s['cal_l_left'],30)
        self.assertGreater(s['cal_l_right']-s['cal_l_center'],30)
        for gaze,direction in ((-12,'LEFT'),(0,'CENTER'),(12,'RIGHT')):
            s=self.observe(gaze,gaze,n=16)
            self.assertEqual(s['direction_name'],direction)

    def test_detector_box_motion_alone_does_not_invent_gaze(self):
        self.calibrate()
        for shift in (-12,12,0,-8,8):
            s=self.observe(0,shift,n=16)
            self.assertEqual(s['direction_name'],'CENTER')
            self.assertEqual(s['event_seq'],0)
            self.assertEqual((s['lx'],s['rx']),(75,185))

    def test_real_head_motion_still_follows_with_eye_box_motion(self):
        self.calibrate()
        for dx,dy,scale in ((24,12,1.),(-20,-8,1.),(10,5,1.2),(-8,4,.85)):
            for gaze,direction in ((-12,'LEFT'),(0,'CENTER'),(12,'RIGHT')):
                s=self.observe(gaze,gaze,dx,dy,scale,n=16)
                self.assertEqual(s['direction_name'],direction,(dx,dy,scale,gaze,s['tracking_reason']))


if __name__=='__main__':unittest.main(verbosity=2)
