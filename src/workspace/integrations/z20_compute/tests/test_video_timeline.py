"""Timestamp annotations stay independent of playback speed and filenames."""
import copy
import unittest

from z20_compute.video_timeline import VideoTimeline


def example():
    entries=[]
    for time,x in ((0.,100),(1.,200)):
        entries.append(dict(time_s=time,person=[x,100,x+40,300],dog=[300,200,400,300],
                            interaction='walking_with_dog',depth_reference=dict(
                                source='size_prior',focal_length_px=600.,principal_point_px=[320.,240.],
                                person=dict(segment_px=[[x,100],[x,300]],length_m=1.7,part='height'),
                                dog=dict(segment_px=[[350,200],[350,300]],length_m=.5,part='height'))))
    return dict(format='z20-video-annotations-v1',image_size=[640,480],duration_s=1.,keyframes=entries)


class VideoTimelineTests(unittest.TestCase):
    def test_midpoint_boxes_and_geometry_come_from_source_timestamp(self):
        timeline=VideoTimeline(example())
        result=timeline.at(.5)
        self.assertEqual(result['boxes']['person'],[150,100,190,300])
        self.assertEqual(result['interaction'],'walking_with_dog')
        self.assertEqual(result['geometry']['person_depth_m'],5.1)
        self.assertEqual(result['annotation_source'],'reviewed_keyframes_interpolated')
        self.assertIsNone(timeline.at(1.01))
        self.assertIsNone(timeline.at(-.01))

    def test_unknown_interval_clears_old_annotation(self):
        data=example();data['keyframes'][1]=dict(time_s=1.,visible=False)
        self.assertIsNone(VideoTimeline(data).at(.5))

    def test_invalid_and_unsorted_timestamps_are_rejected(self):
        for value in (0.,-1.,float('nan')):
            data=copy.deepcopy(example());data['keyframes'][1]['time_s']=value
            with self.assertRaises(ValueError):VideoTimeline(data)
