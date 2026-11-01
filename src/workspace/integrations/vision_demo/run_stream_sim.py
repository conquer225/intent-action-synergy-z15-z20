"""Compile and exercise streaming RTL with the installed Vivado simulator."""
import argparse,subprocess,re
from pathlib import Path
from build_hls import environment
HERE=Path(__file__).resolve().parent

def simulation_passed(text):
    if re.search(r'(?im)^\s*(?:fatal:|error:|error\s*\[)',text):return False
    return any('STREAM_'+key+'_PASS' in text for key in ('PIXELS','VECTORS','HISTORY','CONTROL','720P'))

def vectors(out):
    import numpy as np,cv2
    rng=np.random.default_rng(491);words=[];gold=[]
    for mode in (0,1,4,5,6,7):
        rgb=rng.integers(0,256,(8,16,3),dtype=np.uint8);r=rgb.astype(np.uint32)
        gray=((77*r[...,0]+150*r[...,1]+29*r[...,2]+128)>>8).astype(np.uint8)
        gx=cv2.Sobel(gray,cv2.CV_16S,1,0,ksize=3);gy=cv2.Sobel(gray,cv2.CV_16S,0,1,ksize=3)
        edge=np.minimum(abs(gx)+abs(gy),255).astype(np.uint8);causal=gray.copy();causal[2:,2:]=edge[1:-1,1:-1]
        if mode==0:result=rgb
        elif mode==1:
            magnitude=np.zeros_like(gray);magnitude[2:,2:]=edge[1:-1,1:-1]
            strength=np.where(magnitude>=32,np.minimum(magnitude.astype(int)*2,255),0)
            hue=np.indices(gray.shape)[1]>>3
            colour=np.stack((strength*(64+(hue>>1))>>8,strength*(255-(hue>>1))>>8,strength),axis=-1)
            result=np.minimum((r>>3)+colour,255).astype(np.uint8)
        elif mode==4:result=np.repeat(gray[...,None],3,axis=2)
        elif mode==5:result=np.repeat(np.where(gray>127,255,0)[...,None],3,axis=2)
        else:
            if mode==6:causal[2:,2:]=cv2.medianBlur(gray,3)[1:-1,1:-1]
            result=np.repeat(causal[...,None],3,axis=2)
        for row,store in ((rgb,words),(result,gold)):
            a=row.astype(np.uint32);store.extend(((a[...,0]<<16)|(a[...,1]<<8)|a[...,2]).ravel().tolist())
    for name,data in [('input',words),('golden',gold)]:
        (out/(name+'.hex')).write_text(''.join('%06x\n'%v for v in data),encoding='ascii')

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--full',action='store_true');a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);vectors(out)
    root=Path('D:/vivado/Vivado/2023.1');env=environment(root)
    sources=('vision_stream_histogram.sv','vision_stream_pixels.sv','vision_stream_control.v',
             'tb_stream_pixels.sv','tb_stream_vectors.sv','tb_stream_history.sv','tb_stream_control.sv','tb_stream_720p.sv')
    commands=[('xvlog',['-sv',str(root/'data/verilog/src/glbl.v'),*[str(HERE/'hardware'/n) for n in sources]])]
    tops=['tb_stream_pixels','tb_stream_vectors','tb_stream_history','tb_stream_control']
    if a.full:tops.append('tb_stream_720p')
    for top in tops:commands.extend([('xelab',[top,'glbl','-L','xpm','-s',top]),('xsim',[top,'-runall'])])
    for name,args in commands:
        r=subprocess.run([str(root/'bin/unwrapped/win64.o'/(name+'.exe')),*args],cwd=out,env=env,capture_output=True,text=True)
        text=r.stdout+r.stderr
        (out/(name+'-'+(args[0] if name!='xvlog' else 'compile')+'.txt')).write_text(text,encoding='utf-8')
        print(text[-900:],flush=True)
        if r.returncode:return 1
        if name=='xsim' and not simulation_passed(text):return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
