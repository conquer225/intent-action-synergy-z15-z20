"""Create honest synthetic previews; never labels them as camera or PL evidence."""
import argparse
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from vision_demo.session import VisionSession
from vision_demo.processing import ReferenceProcessor
from vision_demo.pupil import PupilDetector
from vision_demo.presentation import Presenter


def fixture(step=0):
    y,x=np.indices((240,320));rgb=np.empty((240,320,3),np.uint8)
    rgb[...,0]=(x*255//319);rgb[...,1]=(y*255//239);rgb[...,2]=80
    cv2.rectangle(rgb,(30+step*20,50),(120+step*20,140),(230,220,70),-1)
    cv2.circle(rgb,(230-step*10,130),44,(60,200,230),-1)
    rng=np.random.default_rng(12);noise=rng.integers(0,240,(120,2))
    rgb[noise[:,0],noise[:,1]]=255
    return rgb


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('report/preview'))
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    session=VisionSession();presenter=Presenter();thumbs=[]
    for i in range(10):
        proc=ReferenceProcessor();proc.process(fixture(0),session.snapshot()['mode'],reset=True)
        rgb=fixture(1);pupils=None
        if i==9:
            rgb=np.full((240,320,3),180,np.uint8)
            for cx in (100,220):cv2.ellipse(rgb,(cx,120),(11,8),10,0,360,(20,20,20),-1)
            pupils=PupilDetector().detect(rgb,[(65,95,70,50),(185,95,70,50)])
        output=proc.process(rgb,session.snapshot()['mode'])
        rendered=presenter.render(session.snapshot(),output,pupils,backend=proc.backend,fixture=True)
        image=Image.fromarray(rendered);image.save(a.output/('%02d-%s.png'%(i,session.snapshot()['mode'])))
        thumbs.append(image.resize((640,360)));session.next_mode()
    sheet=Image.new('RGB',(1280,1800))
    for i,image in enumerate(thumbs):sheet.paste(image,((i%2)*640,(i//2)*360))
    sheet.save(a.output/'all-modes.png');print(a.output.resolve())


if __name__=='__main__':main()
