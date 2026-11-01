"""OpenCV contour/ellipse pupil candidates. Observation only, no gaze calibration."""
from pathlib import Path
import cv2
import numpy as np


def locate_pupil(gray, roi):
    invalid = dict(valid=False, center=None, ellipse=None, coordinates='source_pixels')
    image=np.asarray(gray)
    if image.dtype!=np.uint8 or image.ndim!=2 or len(roi)!=4:
        return dict(invalid,reason='invalid_input')
    if any(type(v) is not int for v in roi):return dict(invalid,reason='invalid_roi')
    x,y,w,h=roi
    if x<0 or y<0 or w<16 or h<16 or x+w>image.shape[1] or y+h>image.shape[0]:
        return dict(invalid,reason='invalid_roi')
    eye=cv2.medianBlur(image[y:y+h,x:x+w],3)
    if int(eye.max())-int(eye.min())<24:return dict(invalid,reason='low_contrast')
    threshold,_=cv2.threshold(eye,0,255,cv2.THRESH_BINARY_INV|cv2.THRESH_OTSU)
    limit=min(threshold,float(np.percentile(eye,35)))
    levels=np.linspace(float(eye.min())+4,limit,9) if limit>int(eye.min())+4 else [limit]
    candidates=[]
    for level in levels:
        mask=np.uint8(eye<=level)*255
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)))
        contours=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)[-2]
        for contour in contours:
            area=cv2.contourArea(contour)
            if len(contour)<5 or not w*h*.004<=area<=w*h*.22:continue
            (cx,cy),(a,b),angle=cv2.fitEllipse(contour)
            if min(a,b)<3 or max(a,b)>min(w,h)*.75 or min(a,b)/max(a,b)<.55:continue
            if not w*.08<cx<w*.92 or not h*.10<cy<h*.90:continue
            fill=np.zeros_like(eye);cv2.drawContours(fill,[contour],-1,255,-1)
            ring=cv2.dilate(fill,np.ones((7,7),np.uint8)) & ~fill
            if not np.any(ring):continue
            contrast=float(eye[ring!=0].mean())-float(eye[fill!=0].mean())
            ellipse_area=np.pi*a*b/4
            support=area/max(ellipse_area,1)
            if contrast<8 or not .65<=support<=1.25:continue
            score=contrast*min(a,b)/max(a,b)*min(support,1)
            candidates.append((score,dict(valid=True,reason='candidate',center=(cx+x,cy+y),
                ellipse=((cx+x,cy+y),(a,b),angle),coordinates='source_pixels',
                contrast=contrast,backend='PS OpenCV contour/ellipse')))
    candidates.sort(key=lambda row:row[0],reverse=True)
    distinct=[]
    for candidate in candidates:
        cx,cy=candidate[1]['center']
        if not any(np.hypot(cx-row[1]['center'][0],cy-row[1]['center'][1])<4 for row in distinct):
            distinct.append(candidate)
    candidates=distinct
    if not candidates:return dict(invalid,reason='not_found')
    if len(candidates)>1 and candidates[1][0]>=candidates[0][0]*.85:
        return dict(invalid,reason='ambiguous')
    return candidates[0][1]


class PupilDetector:
    def __init__(self, cascade_root=None):
        root=Path(cascade_root or cv2.data.haarcascades)
        cascade=getattr(cv2,'CascadeClassifier',None)
        self.face=cascade(str(root/'haarcascade_frontalface_default.xml')) if cascade else None
        self.eyes=cascade(str(root/'haarcascade_eye_tree_eyeglasses.xml')) if cascade else None
        self.plain_eyes=cascade(str(root/'haarcascade_eye.xml')) if cascade else None
        if cascade and (self.face.empty() or self.eyes.empty() or self.plain_eyes.empty()):raise RuntimeError('Missing OpenCV cascades')

    def detect(self,rgb,rois=None):
        gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
        if rois is None:
            if self.face is None:return dict(valid=False,reason='automatic_roi_backend_unavailable',pupils=[])
            faces=self.face.detectMultiScale(gray,1.1,5,minSize=(80,80))
            if len(faces)!=1:return dict(valid=False,reason='one_face_required',pupils=[])
            x,y,w,h=map(int,faces[0]);upper=gray[y:y+int(h*.65),x:x+w]
            groups=[]
            found=list(self.eyes.detectMultiScale(upper,1.05,3,minSize=(16,16)))
            found+=list(self.plain_eyes.detectMultiScale(upper,1.05,3,minSize=(16,16)))
            for region in found:
                a,b,c,d=map(int,region)
                if not .08*w<c<.45*w or not .12*h<b+d/2<.5*h:continue
                rectangle=(a,b,c,d);matched=False
                for existing in groups:
                    e,f,g,j=existing
                    intersection=max(0,min(a+c,e+g)-max(a,e))*max(0,min(b+d,f+j)-max(b,f))
                    if intersection/max(1,min(c*d,g*j))>.5:matched=True;break
                if not matched:groups.append(rectangle)
            # Require one anatomical pair, rather than selecting two arbitrary blobs.
            if len(groups)!=2:return dict(valid=False,reason='two_eye_regions_required',pupils=[])
            groups.sort();left,right=groups
            lx,ly,lw,lh=left;rx,ry,rw,rh=right
            dx=rx+rw/2-lx-lw/2;dy=abs(ry+rh/2-ly-lh/2)
            if not .2*w<dx<.7*w or dy>.2*h:
                return dict(valid=False,reason='eye_pair_geometry',pupils=[])
            rois=[(x+a,y+b,c,d) for a,b,c,d in groups]
        if len(rois)!=2:return dict(valid=False,reason='two_eye_regions_required',pupils=[])
        pupils=[locate_pupil(gray,tuple(roi)) for roi in rois]
        return dict(valid=any(p['valid'] for p in pupils),reason='candidates',pupils=pupils,
                    backend='PS OpenCV; no calibration writes')
