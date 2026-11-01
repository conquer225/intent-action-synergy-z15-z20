"""Pixel-based registered planar-photo matching for tablet camera inputs."""
import cv2
import numpy as np


class RegisteredPhotos:
    def __init__(self,images):
        if len(images)!=3:raise ValueError('three registered images required')
        self.orb=cv2.ORB_create(nfeatures=2000)
        self.references=[self.orb.detectAndCompute(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY),None)
                         for im in images]
        self.shapes=[im.shape[:2] for im in images]

    def match(self,bgr):
        result=dict(scene_id=None,homography=None,inliers=0,state='unrecognized')
        points,descriptors=self.orb.detectAndCompute(cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY),None)
        if descriptors is None:return result
        matcher=cv2.BFMatcher(cv2.NORM_HAMMING)
        for index,(reference,features) in enumerate(self.references):
            if features is None:continue
            pairs=matcher.knnMatch(features,descriptors,k=2)
            good=[p[0] for p in pairs if len(p)==2 and p[0].distance<.72*p[1].distance]
            if len(good)<15:continue
            a=np.float32([reference[m.queryIdx].pt for m in good])
            b=np.float32([points[m.trainIdx].pt for m in good])
            h,mask=cv2.findHomography(a,b,cv2.RANSAC,3.)
            if h is None or mask is None:continue
            count=int(mask.sum())
            if count<15 or count/len(good)<.45:continue
            height,width=self.shapes[index]
            quad=cv2.perspectiveTransform(np.float32([[[0,0],[width-1,0],
                        [width-1,height-1],[0,height-1]]]),h)[0]
            area=abs(cv2.contourArea(quad))
            if (not cv2.isContourConvex(quad) or area<.04*bgr.shape[0]*bgr.shape[1]
                    or area>1.5*bgr.shape[0]*bgr.shape[1]
                    or not np.isfinite(quad).all()):continue
            if count>result['inliers']:
                result=dict(scene_id=index,homography=h.tolist(),inliers=count,
                            state='registered_photo')
        return result
