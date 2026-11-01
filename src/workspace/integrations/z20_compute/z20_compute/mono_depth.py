"""Optional PC YOLO26-depth preview; network output and metric validation are distinct."""
import argparse
import hashlib
import json
import time
from pathlib import Path
import cv2
import numpy as np

from .depth_surface import depth_surface, write_surface_ply


class YoloDepthRunner:
    """Load one optional PC model and reuse it across independently received frames."""
    def __init__(self, model_path, *, device='cpu', imgsz=768):
        from ultralytics import YOLO
        import ultralytics
        self.model = YOLO(str(model_path), task='depth')
        self.device, self.imgsz = device, imgsz
        checkpoint = Path(str(getattr(self.model, 'ckpt_path', model_path)))
        self.metadata = dict(model=Path(model_path).name, device=device, imgsz=imgsz,
                             ultralytics_version=ultralytics.__version__)
        if checkpoint.is_file():
            self.metadata['model_sha256'] = hashlib.sha256(checkpoint.read_bytes()).hexdigest()

    def infer(self, image):
        start = time.perf_counter()
        result = self.model.predict(image, device=self.device, imgsz=self.imgsz, verbose=False)[0]
        depth = result.depth.data.detach().cpu().numpy().squeeze()
        return depth, {**self.metadata, 'prediction_elapsed_s': time.perf_counter()-start,
                       'model_speed_ms': result.speed}


def process_monocular_frame(sequence, bgr, output, *, infer, focal_px):
    depth, metadata = infer(bgr)
    directory = Path(output)/f'frame-{sequence:010d}'
    record = export_monocular_preview(bgr, depth, directory, focal_px=focal_px,
                                       model_name=metadata['model'])
    record.update(metadata, sequence=sequence, valid=True, frame_directory=directory.name)
    directory.joinpath('result.json').write_text(
        json.dumps(record, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    Path(output, 'latest.json').write_text(
        json.dumps(record, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return record


def export_monocular_preview(bgr, depth, output, *, focal_px, model_name, stride=2):
    depth = np.asarray(depth, np.float32)
    if depth.shape != bgr.shape[:2]:
        raise ValueError('depth must align exactly with input image')
    valid = np.isfinite(depth) & (depth > 0)
    if int(valid.sum()) < 4:
        raise ValueError('not enough positive finite model depth values')
    scale = float(np.median(depth[valid]))
    relative = depth / scale
    relative[~valid] = np.nan
    h, w = depth.shape
    K = np.array([[focal_px, 0, (w-1)/2], [0, focal_px, (h-1)/2], [0, 0, 1.]])
    surface = depth_surface(relative, bgr, K, stride=stride)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    np.save(output/'depth-raw.npy', depth, allow_pickle=False)
    np.save(output/'depth-relative.npy', relative, allow_pickle=False)
    cv2.imwrite(str(output/'input.png'), bgr)
    comment = 'monocular_prediction; median_depth=1; assumed_intrinsics; metric_verified=false'
    write_surface_ply(output/'surface.ply', surface, provenance=comment)
    write_surface_ply(output/'cloud.ply', surface, provenance=comment, mesh=False)
    low, high = np.percentile(relative[valid], [2, 98])
    normalized = np.zeros(depth.shape, np.float32)
    if high > low:
        normalized[valid] = np.clip((relative[valid]-low)/(high-low), 0, 1)
    colored = cv2.applyColorMap(np.uint8(normalized*255), cv2.COLORMAP_TURBO)
    colored[~valid] = 0
    cv2.imwrite(str(output/'depth-preview.png'), colored)
    record = dict(depth_source='monocular_model_prediction', model=model_name,
                  metric_verified=False, geometry_verified=False,
                  coordinate_units='relative_depth_median', raw_depth_median=scale,
                  assumed_intrinsics=K.tolist(), image_size=[w, h],
                  input_pixels_sha256=hashlib.sha256(bgr.tobytes()).hexdigest(),
                  vertices=len(surface.vertices), triangles=len(surface.faces),
                  valid_depth_fraction=float(valid.mean()), mesh_stride=stride,
                  mesh_max_relative_depth_jump=.08,
                  raw_prediction_range=np.percentile(depth[valid], [2, 50, 98]).tolist())
    (output/'result.json').write_text(json.dumps(record, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description='PC YOLO26 monocular depth and visible-surface preview')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--npy', type=Path, help='legacy saved 720x1280 BGR stereo capture')
    source.add_argument('--image', type=Path)
    parser.add_argument('--view', type=int, choices=(0, 1), default=0)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', default='yolo26n-depth.pt')
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--imgsz', type=int, default=768)
    parser.add_argument('--focal-px', type=float, default=600., help='assumed focal length at input width')
    args = parser.parse_args(argv)
    if args.npy:
        image = np.load(args.npy, allow_pickle=False)
        if image.shape != (720, 1280, 3) or image.dtype != np.uint8:
            raise ValueError('legacy capture must be uint8 720x1280 BGR')
        image = cv2.resize(image[:, args.view*640:(args.view+1)*640], (640, 480))
        preprocessing = 'legacy_full_sensor_squeezed_half_restored_to_640x480'
    else:
        image = cv2.imread(str(args.image))
        if image is None:
            raise ValueError('cannot read source image')
        preprocessing = 'input_image_unchanged'
    runner = YoloDepthRunner(args.model, device=args.device, imgsz=args.imgsz)
    depth, metadata = runner.infer(image)
    record = export_monocular_preview(image, depth, args.output, focal_px=args.focal_px,
                                       model_name=Path(args.model).name)
    record.update(metadata, preprocessing=preprocessing)
    (args.output/'result.json').write_text(json.dumps(record, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
