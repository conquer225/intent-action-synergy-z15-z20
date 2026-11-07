"""Fixed-point point-cloud projection, depth rasterization and trajectory."""
import numpy as np

from .fixed import round_shift

MAP_MAGIC = 0x4d415031
MAX_POINTS, MAX_TRAJECTORY = 65536, 1024


def _coordinates(values, name, maximum):
    array = np.asarray(values, np.float64)
    if not array.size:
        array = np.empty((0, 3), np.float64)
    if (array.ndim != 2 or array.shape[1] != 3 or len(array) > maximum
            or not np.isfinite(array).all() or np.max(np.abs(array), initial=0) > 2048):
        raise ValueError(name + ' must be bounded finite XYZ rows')
    return array


def _q16(values):
    values = np.asarray(values, np.float64)
    return (np.sign(values)*np.floor(np.abs(values)*65536+.5)).astype(np.int32)


def _color(rgb):
    return int(rgb[0]) << 16 | int(rgb[1]) << 8 | int(rgb[2])


class MapScene:
    def __init__(self, points, *, colors=None, trajectory=(), width=640, height=480,
                 focal=400., center=None, camera=None, near=.05, far=1000., radius=0,
                 units='m', frame_id='', sequence=0):
        self.points = _coordinates(points, 'points', MAX_POINTS)
        self.trajectory = _coordinates(trajectory, 'trajectory', MAX_TRAJECTORY)
        if (type(width) is not int or type(height) is not int or not 1 <= width <= 1280
                or not 1 <= height <= 720 or type(radius) is not int or not 0 <= radius <= 2
                or not np.isfinite([focal, near, far]).all() or not 0 < focal <= 4096
                or not 0 < near < far <= 2048 or not 0 <= sequence <= 0x7fffffff):
            raise ValueError('map projection configuration')
        self.width, self.height, self.radius, self.sequence = width, height, radius, sequence
        if colors is None:
            colors = np.tile([90, 210, 240], (len(self.points), 1))
        colors = np.asarray(colors)
        if colors.shape != self.points.shape or colors.dtype.kind not in 'iu' or np.any(colors < 0) or np.any(colors > 255):
            raise ValueError('colors must be RGB bytes matching points')
        self.colors = colors.astype(np.uint8)
        camera = np.eye(4) if camera is None else np.asarray(camera, np.float64)
        if (camera.shape != (4, 4) or not np.isfinite(camera).all() or np.max(np.abs(camera)) > 2048
                or not np.allclose(camera[3], [0, 0, 0, 1])):
            raise ValueError('camera transform must be a bounded homogeneous 4x4 matrix')
        self.camera = _q16(camera[:3])
        center = (width/2, height/2) if center is None else center
        if len(center) != 2 or not np.isfinite(center).all() or np.max(np.abs(center)) > 4096:
            raise ValueError('projection center')
        self.projection = _q16([focal, focal, *center])
        self.near, self.far = int(_q16(near)), int(_q16(far))
        if self.near < 1:
            raise ValueError('near plane must occupy a positive Q16 value')
        self.metadata = dict(units=str(units), frame_id=str(frame_id), sequence=sequence)

    def vertex_words(self):
        xyz = _q16(np.concatenate((self.points, self.trajectory)))
        rgba = np.asarray([_color(c) for c in self.colors]+[0xffc440]*len(self.trajectory), np.int32)
        return np.column_stack((xyz, rgba)).astype(np.int32).ravel()

    def parameter_words(self):
        header = [MAP_MAGIC, 1, self.width, self.height, len(self.points), len(self.trajectory),
                  self.near, self.far, self.radius, 0x0c121c, 0xffc440, self.sequence]
        return np.asarray(header+self.camera.ravel().tolist()+self.projection.tolist()+[0]*4, np.int32)


def project(scene, xyz):
    coordinates = [round_shift(sum(int(w)*int(v) for w, v in zip(row, [*xyz, 65536])), 16)
                   for row in scene.camera]
    x, y, z = coordinates
    if z < scene.near or z > scene.far or any(abs(v) >= 1 << 31 for v in coordinates):
        return None
    fx, fy, cx, cy = map(int, scene.projection)
    # Division truncates toward zero, matching the signed HLS division.
    divide = lambda v: (abs(v)//z)*(-1 if v < 0 else 1)
    u = round_shift(divide(fx*x)+cx, 16)
    v = round_shift(divide(fy*y)+cy, 16)
    if abs(u) > 1048576 or abs(v) > 1048576:
        return None
    return u, v, z


def clipped_line(a, b, width, height):
    """Integer Cohen-Sutherland with bounded intersections and inclusive edges."""
    x0, y0 = a;x1, y1 = b
    def code(x, y):
        return (1 if x < 0 else 2 if x >= width else 0) | (4 if y < 0 else 8 if y >= height else 0)
    def div(a, b):
        return (abs(a)//abs(b))*(-1 if (a < 0) != (b < 0) else 1)
    for _ in range(8):
        c0, c1 = code(x0, y0), code(x1, y1)
        if not c0 and not c1:
            return (x0, y0), (x1, y1)
        if c0 & c1:
            return None
        c = c0 or c1
        if c & 8:
            y = height-1;x = x0+div((x1-x0)*(y-y0), y1-y0)
        elif c & 4:
            y = 0;x = x0+div((x1-x0)*(-y0), y1-y0)
        elif c & 2:
            x = width-1;y = y0+div((y1-y0)*(x-x0), x1-x0)
        else:
            x = 0;y = y0+div((y1-y0)*(-x0), x1-x0)
        if c == c0:x0, y0 = x, y
        else:x1, y1 = x, y
    return None


def render_reference(scene):
    frame = np.full((scene.height, scene.width), 0x0c121c, np.int32)
    depth = np.full(frame.shape, 0x7fffffff, np.int32)
    vertices = scene.vertex_words().reshape(-1, 4)
    visible = clipped = segments = 0
    for row in vertices[:len(scene.points)]:
        value = project(scene, row[:3])
        if value is None or not (0 <= value[0] < scene.width and 0 <= value[1] < scene.height):
            clipped += 1;continue
        u, v, z = value;visible += 1
        for y in range(max(0, v-scene.radius), min(scene.height, v+scene.radius+1)):
            for x in range(max(0, u-scene.radius), min(scene.width, u+scene.radius+1)):
                if z < depth[y, x]:
                    depth[y, x] = z;frame[y, x] = row[3]
    previous = None
    for row in vertices[len(scene.points):]:
        value = project(scene, row[:3])
        if value is not None and previous is not None:
            line = clipped_line(previous[:2], value[:2], scene.width, scene.height)
            if line:
                (x, y), (x1, y1) = line;dx, dy = abs(x1-x), -abs(y1-y)
                sx, sy = (1 if x < x1 else -1), (1 if y < y1 else -1)
                error = dx+dy
                while True:
                    frame[y, x] = 0xffc440
                    if x == x1 and y == y1:break
                    twice = 2*error
                    if twice >= dy:error += dy;x += sx
                    if twice <= dx:error += dx;y += sy
                segments += 1
        previous = value
    rgb = np.stack(((frame >> 16) & 255, (frame >> 8) & 255, frame & 255), axis=-1).astype(np.uint8)
    return rgb, dict(visible_points=visible, clipped_points=clipped,
                     trajectory_segments=segments, **scene.metadata)
