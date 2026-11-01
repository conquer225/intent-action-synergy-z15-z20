"""Compare native C classifier decisions with direct XML/NumPy evaluation.

The reference sums pixels directly (no integral image or generated C tables).
Optional --sample supplies a local face image to add positive windows.
"""
import argparse
import ctypes as C
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / 'local/face_reference_env'))
import numpy as np

def read_model(name):
    m = ET.parse(ROOT / 'model' / name).getroot().find('cascade')
    features = [[tuple(map(float, r.text.split())) for r in f.find('rects')]
                for f in m.find('features')]
    stages = []
    for stage in m.find('stages'):
        weak = []
        for node in stage.find('weakClassifiers'):
            internal = node.findtext('internalNodes').split()
            weak.append((int(internal[2]), np.float32(internal[3]),
                         *map(np.float32, node.findtext('leafValues').split())))
        stages.append((np.float32(float(stage.findtext('stageThreshold')) - 1e-5), weak))
    return int(m.findtext('width')), features, stages

def reference(p, features, stages):
    q = p[1:-1, 1:-1].astype(np.int64)
    variance = q.size * int((q*q).sum()) - int(q.sum())**2
    if variance <= q.size*q.size*100:
        return -1
    norm = np.float32(1/math.sqrt(variance))
    for index, (threshold, weak) in enumerate(stages):
        total = 0.0
        for feature, split, left, right in weak:
            value = np.float32(0)
            for x, y, w, h, weight in features[feature]:
                x, y, w, h = map(int, (x, y, w, h))
                value = np.float32(value + np.float32(weight)*np.float32(p[y:y+h,x:x+w].sum()))
            total += float(left if np.float32(value*norm) < split else right)
        if total < threshold:
            return -index
    return 1

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sample', type=Path)
    args = parser.parse_args()
    lib = C.CDLL(str(ROOT/'tests/localize.dll'))
    lib.haar_window.argtypes = [C.c_void_p, C.c_int, C.c_int]
    rng = np.random.default_rng(2918)
    results = []
    for kind, name in enumerate(('haarcascade_frontalface_default.xml',
                                  'haarcascade_eye.xml', 'haarcascade_frontalface_alt.xml')):
        size, features, stages = read_model(name)
        patches = [np.full((size,size), v, np.uint8) for v in (0,51,128,255)]
        patches += [rng.integers(0,256,(size,size),dtype=np.uint8) for _ in range(160)]
        # Stripe, gradient, and low-variance negatives stress rectangle sums.
        for axis in (0,1):
            p = np.indices((size,size))[axis]
            for period in (2,3,5,7):
                patches.append(((p//period)%2*255).astype(np.uint8))
        if args.sample:
            import cv2
            im = cv2.imread(str(args.sample), cv2.IMREAD_GRAYSCALE)
            if im is None:
                raise ValueError('Cannot read sample: '+str(args.sample))
            gray = cv2.equalizeHist(im)
            detector = cv2.CascadeClassifier(str(ROOT/'model'/name))
            boxes = detector.detectMultiScale(gray, 1.05, 3, minSize=(size,size))
            for x,y,w,h in boxes:
                # Cover neighboring windows around an independent OpenCV detection.
                for scale in (0.9,1.0,1.1):
                    extent = int(w*scale)
                    for dx in (-0.06,0,0.06):
                        for dy in (-0.06,0,0.06):
                            xx = int(x+(w-extent)/2+dx*w)
                            yy = int(y+(h-extent)/2+dy*h)
                            if min(xx,yy)>=0 and xx+extent<=gray.shape[1] and yy+extent<=gray.shape[0]:
                                patches.append(cv2.resize(gray[yy:yy+extent,xx:xx+extent],(size,size)))
        positives = 0
        for index, patch in enumerate(patches):
            patch = np.ascontiguousarray(patch)
            actual = lib.haar_window(patch.ctypes.data, size, kind)
            expected = reference(patch, features, stages)
            assert actual == expected, (name,index,actual,expected)
            positives += actual > 0
        if args.sample:
            assert positives > 0, (name, 'no positive test windows')
        results.append(dict(model=name, windows=len(patches), positives=positives, mismatches=0))
    report = dict(reference='Direct XML rectangles and stage decisions, native scale', results=results)
    (ROOT/'report/haar_reference.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__ == '__main__':
    main()
