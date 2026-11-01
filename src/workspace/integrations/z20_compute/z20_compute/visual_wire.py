"""Bounded JSON controls and JPEG envelopes, independent of packet boundaries."""
import json
import re
import struct
import numpy as np

MAX_JSON=65536
MAX_JPEG=1024*1024


def _reject_constant(value):
    raise ValueError('non-finite JSON value')


def read_json(stream):
    raw=stream.readline(MAX_JSON+1)
    if not raw:raise EOFError('connection closed')
    if len(raw)>MAX_JSON or not raw.endswith(b'\n'):raise ValueError('JSON line too long or incomplete')
    value=json.loads(raw.decode('utf-8'),parse_constant=_reject_constant)
    if not isinstance(value,dict):raise ValueError('expected JSON object')
    return value


def write_json(stream,value):
    raw=json.dumps(value,allow_nan=False,separators=(',',':')).encode('utf-8')+b'\n'
    if len(raw)>MAX_JSON:raise ValueError('JSON object exceeds bound')
    stream.write(raw);stream.flush()


def _frame_meta(meta):
    if (not isinstance(meta.get('session'),str) or not re.fullmatch('[0-9a-f]{32}',meta['session'])
            or any(type(meta.get(k)) is not int or meta[k]<0 for k in ('epoch','sequence','length'))
            or not 1<=meta['length']<=MAX_JPEG):
        raise ValueError('invalid frame envelope')


def read_frame(stream):
    meta=read_json(stream);_frame_meta(meta)
    data=bytearray()
    while len(data)<meta['length']:
        part=stream.read(meta['length']-len(data))
        if not part:raise EOFError('truncated frame')
        data.extend(part)
    return meta,bytes(data)


def write_frame(stream,session,epoch,sequence,jpeg):
    meta=dict(session=session,epoch=epoch,sequence=sequence,length=len(jpeg))
    _frame_meta(meta);write_json(stream,meta);stream.write(jpeg);stream.flush()


def jpeg_dimensions(data):
    if not isinstance(data,bytes) or not 4<=len(data)<=MAX_JPEG or data[:2]!=b'\xff\xd8':
        raise ValueError('invalid JPEG')
    offset=2
    while offset+4<=len(data):
        if data[offset]!=255:raise ValueError('malformed JPEG marker')
        while offset<len(data) and data[offset]==255:offset+=1
        if offset>=len(data):break
        marker=data[offset];offset+=1
        if marker in (0xd9,0xda):break
        if marker==0x01 or 0xd0<=marker<=0xd7:continue
        if offset+2>len(data):break
        size=struct.unpack_from('>H',data,offset)[0]
        if size<2 or offset+size>len(data):raise ValueError('truncated JPEG segment')
        if marker in (0xc0,0xc1,0xc2):
            if size<8:raise ValueError('invalid JPEG SOF')
            height,width=struct.unpack_from('>HH',data,offset+3)
            if not 1<=width<=1280 or not 1<=height<=720:raise ValueError('JPEG dimensions out of bounds')
            return width,height
        offset+=size
    raise ValueError('JPEG missing supported SOF')


def decode_jpeg(data):
    jpeg_dimensions(data)
    import cv2
    bgr=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
    if bgr is None:raise ValueError('JPEG decoding failed')
    height,width=bgr.shape[:2];scale=min(1280./width,720./height)
    w,h=max(1,int(width*scale)),max(1,int(height*scale))
    output=np.zeros((720,1280,3),np.uint8)
    output[(720-h)//2:(720-h)//2+h,(1280-w)//2:(1280-w)//2+w]=cv2.resize(bgr,(w,h))[...,::-1]
    return output
