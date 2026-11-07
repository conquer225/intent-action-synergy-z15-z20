"""Render deterministic C++ kernel scenes and export EEG comparison data."""
import argparse
import csv
import ctypes
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/workspace/integrations'))
from pl_accel.mapping import render_reference
from pl_accel.view import MapView


def vector(path, name):
    match = re.search(name+r'\[\d+\]=\{(.*?)\};', path.read_text(encoding='ascii'), re.S)
    return np.array([int(value) for value in match[1].replace('\n', '').split(',')], np.int32)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = ROOT/'src/workspace/integrations/pl_accel/hls'
    library = args.output/('kernels.dll' if sys.platform == 'win32' else 'kernels.so')
    subprocess.run([shutil.which('g++') or 'g++', '-std=c++14', '-shared', '-O2', '-Wno-unknown-pragmas',
        str(source/'eeg.cpp'), str(source/'map.cpp'), '-o', str(library)], check=True)
    dll = ctypes.CDLL(str(library.resolve()))
    pointer = np.ctypeslib.ndpointer(dtype=np.int32, flags='C_CONTIGUOUS')
    dll.z20_map.argtypes = [pointer]*5;dll.z20_map.restype = None
    dll.z15_fbcsp.argtypes = [pointer, pointer, pointer, ctypes.c_uint, ctypes.c_uint];dll.z15_fbcsp.restype = None
    reports, images = [], []
    class Backend:
        def render(self, scene):
            frame, depth, stats = np.zeros(scene.width*scene.height,np.int32), np.zeros(scene.width*scene.height,np.int32), np.zeros(16,np.int32)
            dll.z20_map(scene.vertex_words(),scene.parameter_words(),frame,depth,stats)
            rgb = np.stack(((frame>>16)&255,(frame>>8)&255,frame&255),axis=-1).astype(np.uint8).reshape(scene.height,scene.width,3)
            expected, reference_stats = render_reference(scene)
            errors = int(np.count_nonzero(np.any(rgb != expected, axis=-1)))
            if errors or stats[1]:raise ValueError('C++ map frame differs from integer reference')
            reports.append(dict(pixel_mismatches=errors, visible_points=int(stats[2]), width=scene.width,height=scene.height))
            return rgb, reference_stats
    x, y = np.meshgrid(np.linspace(-1.2,1.2,180), np.linspace(-.8,.8,120))
    z = 2+.25*np.sin(3*x)*np.cos(3*y)+.15*(x*x+y*y)
    points = np.column_stack((x.ravel(),y.ravel(),z.ravel()))
    colors = np.column_stack((np.rint((x.ravel()+1.2)/2.4*150+70),
        np.rint((y.ravel()+.8)/1.6*130+70), np.rint((z.ravel()-1.7)*70+50))).astype(np.uint8)
    t=np.linspace(-1,1,80)
    geometry = SimpleNamespace(points=points,colors=colors,trajectory=np.column_stack((t,.7*np.sin(2*t),np.full_like(t,1.7))),
        units='scene_units',frame_id='analytic-surface-v1',metric_verified=False)
    view = MapView(Backend())
    for index in range(3):
        frame, _ = view.render_geometry(geometry,view=index,sequence=index)
        picture=Image.fromarray(frame);picture.save(args.output/('map_'+str(index)+'.png'))
        images.append(picture.resize((960,540)))
    images[0].save(args.output/'pl_map.gif',save_all=True,append_images=images[1:],duration=1100,loop=0)
    params=vector(source/'eeg_vectors.h','eeg_fixture_params')
    samples=vector(source/'eeg_vectors.h','eeg_fixture_samples').reshape(-1,8)
    expected=vector(source/'eeg_vectors.h','eeg_fixture_expected').reshape(-1,10)
    result=np.zeros(16,np.int32);rows=[]
    for start in range(0,len(samples),16):
        dll.z15_fbcsp(np.ascontiguousarray(samples[start:start+16]).ravel(),params,result,16,start==0)
        if result[1]&1:
            rows.append([int((result[1]>>1)&1),int(result[4]),int(result[5]),*result[8:14].tolist(),int(result[2])])
    rows=np.asarray(rows,np.int32)
    if not np.array_equal(rows,expected):raise ValueError('C++ EEG fixture differs from integer reference')
    with (args.output/'eeg_features.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['valid','class_id','score_q24',*[f'feature_{i}_q12' for i in range(6)],'sample_count']);writer.writerows(rows.tolist())
    report=dict(scope='host_C++_kernels_with_independent_integer_references',
        map=dict(input_points=len(points),trajectory_points=len(t),views=reports),
        eeg=dict(input_samples=len(samples),channels=8,windows=len(rows),feature_mismatches=0,score_mismatches=0))
    (args.output/'numeric_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':main()
