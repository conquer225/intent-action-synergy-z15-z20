"""Reference-size pinhole estimates for registered monocular photographs."""
import math
from numbers import Real


def _number(value):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError('reference geometry requires finite numeric values')
    return float(value)


def _pixel(point, size):
    if not isinstance(point, (list, tuple)) or len(point) != 2:
        raise ValueError('reference point must have two pixel coordinates')
    x, y = [_number(v) for v in point]
    if not (0 <= x < size[0] and 0 <= y < size[1]):
        raise ValueError('reference point outside image')
    return x, y


def estimate_geometry(annotation, size):
    """Use Z=f*L/l and box centers; absent references produce no metric result.

    The reference segment represents a known/prior length parallel to the image
    plane at the object's depth. Square pixels and one focal length are used.
    Every current gallery reference is a size prior, so results stay estimated.
    """
    reference = annotation.get('depth_reference')
    if reference is None:
        return None
    if tuple(size) != (640, 480) or reference.get('source') != 'size_prior':
        raise ValueError('expected labelled 640x480 size-prior geometry')
    focal = _number(reference.get('focal_length_px'))
    if focal <= 0:
        raise ValueError('focal length must be positive')
    cx, cy = _pixel(reference.get('principal_point_px'), size)
    points = {}
    for label in ('person', 'dog'):
        item = reference.get(label, {})
        segment = item.get('segment_px')
        if not isinstance(segment, (list, tuple)) or len(segment) != 2:
            raise ValueError('reference segment needs two endpoints')
        a, b = [_pixel(point, size) for point in segment]
        pixels = math.hypot(b[0] - a[0], b[1] - a[1])
        length = _number(item.get('length_m'))
        if pixels <= 0 or length <= 0 or not item.get('part'):
            raise ValueError('reference segment and physical length must be positive')
        z = focal * length / pixels
        x0, y0, x1, y1 = annotation[label]
        u, v = (x0 + x1) / 2., (y0 + y1) / 2.
        points[label] = [(u - cx) * z / focal, (v - cy) * z / focal, z]
    distance = math.sqrt(sum((a - b) ** 2 for a, b in
                             zip(points['person'], points['dog'])))
    return dict(status='estimated', method='reference-size-pinhole-v1',
                reference_source=reference['source'], reference_inputs=reference,
                coordinate_frame='camera_xyz_m',
                distance_definition='box_center_to_box_center',
                person_depth_m=points['person'][2], dog_depth_m=points['dog'][2],
                person_xyz_m=points['person'], dog_xyz_m=points['dog'],
                distance_m=distance)
