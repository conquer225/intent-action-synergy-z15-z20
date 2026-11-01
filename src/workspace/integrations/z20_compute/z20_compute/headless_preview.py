"""Lossless RGB preview without Pillow/cv2; publisher is the display owner."""
import hashlib
import json
from pathlib import Path
import struct
import time
import zlib
import numpy as np


def _chunk(kind, data):
    return struct.pack('!I', len(data))+kind+data+struct.pack('!I', zlib.crc32(kind+data) & 0xffffffff)


def publish_frame(path, frame, *, now=None, result=None, display_equal=None):
    if not isinstance(frame, np.ndarray) or frame.shape != (720, 1280, 3) or frame.dtype != np.uint8:
        raise ValueError('expected RGB720p uint8 frame')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = np.ascontiguousarray(frame)
    filtered = np.zeros((720, 3841), np.uint8)
    filtered[:, 1:] = frame.reshape(720, 3840)
    png = (b'\x89PNG\r\n\x1a\n'+_chunk(b'IHDR', struct.pack('!IIBBBBB', 1280, 720, 8, 2, 0, 0, 0))+
           _chunk(b'IDAT', zlib.compress(filtered.tobytes(), 1))+_chunk(b'IEND', b''))
    metadata = dict(published_unix=time.time() if now is None else now, width=1280, height=720,
        rgb_sha256=hashlib.sha256(frame.tobytes()).hexdigest(),
        png_sha256=hashlib.sha256(png).hexdigest(), display_buffer_equal=display_equal, result=result)
    temporary = path.with_suffix('.png.tmp')
    temporary.write_bytes(png); temporary.replace(path)
    info = path.with_suffix('.json'); temporary = info.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(metadata, allow_nan=False), encoding='utf-8'); temporary.replace(info)
    return metadata


def preview_fresh(path, *, now=None):
    path = Path(path)
    try:
        metadata = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
        age = (time.time() if now is None else now)-metadata['published_unix']
        return (0 <= age < 3 and path.stat().st_size <= 4*1024*1024
                and hashlib.sha256(path.read_bytes()).hexdigest() == metadata['png_sha256'])
    except (OSError, ValueError, KeyError, TypeError):
        return False
