"""Offline reference illustrations for VIS2. Never imported by the live renderer."""
import argparse
from pathlib import Path
import cv2,numpy as np
from PIL import Image,ImageDraw
from vision_demo.presentation import Presenter
from vision_demo.session import MODES

def process(rgb,mode,previous=None):
    r=rgb.astype(np.uint32);height,width=rgb.shape[:2]
    gray=((77*r[...,0]+150*r[...,1]+29*r[...,2]+128)>>8).astype(np.uint8)
    state={};hue=np.indices(gray.shape)[1]>>3
    def colour(strength,dark,phase=hue):
        c=np.stack((strength*(64+(phase>>1))>>8,strength*(255-(phase>>1))>>8,strength),axis=-1)
        return np.minimum((r>>(3 if dark else 1))+c,255).astype(np.uint8)
    if mode==0:result=rgb.copy()
    elif mode in (1,6,7):
        if mode==6:v=cv2.medianBlur(gray,3)
        else:
            gx=cv2.Sobel(gray,cv2.CV_16S,1,0,ksize=3);gy=cv2.Sobel(gray,cv2.CV_16S,0,1,ksize=3)
            v=np.minimum(abs(gx)+abs(gy),255).astype(np.uint8)
        causal=gray.copy();causal[2:,2:]=v[1:-1,1:-1]
        if mode==1:
            causal[:2]=0;causal[:,:2]=0
            strength=np.where(causal>=32,np.minimum(causal.astype(int)*2,255),0)
            result=colour(strength,True)
        else:result=np.repeat(causal[...,None],3,axis=2)
    elif mode in (2,3):
        grid=gray[::4,::4].astype(int)
        if previous is None:delta=np.zeros_like(grid);trail=delta.copy()
        else:
            delta=abs(grid-previous['gray']);old=previous['trail']
            trail=np.maximum(delta,old-(old>>3)-(old!=0))
        state=dict(gray=grid,trail=trail)
        magnitude=trail if mode==2 else delta
        magnitude=np.repeat(np.repeat(magnitude,4,axis=0),4,axis=1)[:height,:width]
        strength=np.where(magnitude>(16 if mode==2 else 20),np.minimum(magnitude*4,255),0)
        result=colour(strength,False,hue if mode==2 else np.full_like(hue,220))
    elif mode==4:result=np.repeat(gray[...,None],3,axis=2)
    elif mode==5:result=np.repeat(np.where(gray>127,255,0)[...,None],3,axis=2).astype(np.uint8)
    elif mode==8:
        mapping=previous['mapping'] if previous else np.arange(256,dtype=np.uint8)
        result=np.repeat(mapping[gray][...,None],3,axis=2)
        counts=np.bincount(gray.ravel(),minlength=256);first=np.flatnonzero(counts)[0]
        denominator=gray.size-counts[first]
        mapping=np.arange(256,dtype=np.uint8)
        if denominator:mapping=np.clip((np.cumsum(counts)-counts[first])*255//denominator,0,255).astype(np.uint8)
        state=dict(mapping=mapping)
    else:raise ValueError('Only ordinary OV5640 modes are illustrated')
    return result,state

def fixture(step):
    y,x=np.indices((720,1280));a=np.empty((720,1280,3),np.uint8)
    a[...,0]=20+x*35//1279;a[...,1]=35+y*75//719;a[...,2]=65+y*70//719
    for k in range(8):
        left=40+k*155;top=180+(k%3)*55
        cv2.rectangle(a,(left,top),(left+115,650),(45+k*12,75+k*12,105+k*10),-1)
        for yy in range(top+20,620,45):
            for xx in range(left+15,left+100,30):cv2.rectangle(a,(xx,yy),(xx+12,yy+20),(180,180,95),-1)
    cv2.circle(a,(360+step*70,350),115,(235,110,60),-1)
    cv2.ellipse(a,(900-step*45,390),(110,150),20,0,360,(60,205,205),-1)
    cv2.line(a,(90,660),(1180,660),(235,220,170),5)
    return a

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('report/stream-preview'));a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);presenter=Presenter();thumbnails=[]
    for mode,(name,label) in enumerate(MODES[:9]):
        _,state=process(fixture(0),mode);rgb,_=process(fixture(1),mode,state)
        canvas=Image.new('RGB',(1280,768),(12,17,25));canvas.paste(Image.fromarray(rgb),(0,0))
        draw=ImageDraw.Draw(canvas);presenter.text(draw,(18,730),'%02d %s  /  合成素材 · CPU 参考效果 · 非实机画面'%(mode+1,label),presenter.body,(220,230,240))
        canvas.save(a.output/('%02d-%s.png'%(mode,name)));thumbnails.append(canvas.resize((640,384)))
    grid=Image.new('RGB',(1280,1920),(12,17,25))
    for i,thumbnail in enumerate(thumbnails):grid.paste(thumbnail,((i%2)*640,(i//2)*384))
    grid.save(a.output/'all-stream-modes.png');print(a.output.resolve())
if __name__=='__main__':main()
