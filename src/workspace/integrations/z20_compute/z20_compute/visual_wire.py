"""Bounded JSON controls and JPEG envelopes, independent of packet boundaries."""
import json
import re
import struct
import numpy as np

MAX_JSON=65536
MAX_JPEG=1024*1024
MAX_GEOMETRY=(65536+1024)*16


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
    geometry=meta.get('kind')=='geometry'
    maximum=MAX_GEOMETRY if geometry else MAX_JPEG
    if (not isinstance(meta.get('session'),str) or not re.fullmatch('[0-9a-f]{32}',meta['session'])
            or any(type(meta.get(k)) is not int or meta[k]<0 for k in ('epoch','sequence','length'))
            or meta.get('kind') not in (None,'jpeg','geometry')
            or not (0 if geometry else 1)<=meta['length']<=maximum):
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


class GeometryFrame:
    """Owned geometry; coordinate units and source identity survive transport."""
    def __init__(self,points,colors=None,*,trajectory=(),units='m',frame_id='',metric_verified=False):
        def xyz(value,maximum):
            value=np.asarray(value,np.float64)
            if not value.size:value=np.empty((0,3),np.float64)
            if (value.ndim!=2 or value.shape[1]!=3 or len(value)>maximum
                    or not np.isfinite(value).all() or np.max(np.abs(value),initial=0)>2048):
                raise ValueError('geometry coordinates exceed contract')
            result=np.array(value,copy=True);result.flags.writeable=False;return result
        self.points,self.trajectory=xyz(points,65536),xyz(trajectory,1024)
        if colors is None:colors=np.tile([90,210,240],(len(self.points),1))
        colors=np.asarray(colors)
        if colors.shape!=self.points.shape or colors.dtype.kind not in 'iu' or np.any(colors<0) or np.any(colors>255):
            raise ValueError('geometry RGB contract')
        self.colors=colors.astype(np.uint8,copy=True);self.colors.flags.writeable=False
        if (not isinstance(units,str) or not 1<=len(units)<=64 or not isinstance(frame_id,str)
                or len(frame_id)>128 or type(metric_verified) is not bool):raise ValueError('geometry metadata')
        self.units,self.frame_id,self.metric_verified=units,frame_id,metric_verified

    def packed(self):
        xyz=np.concatenate((self.points,self.trajectory))
        rows=np.zeros((len(xyz),4),dtype='<i4')
        rows[:,:3]=(np.sign(xyz)*np.floor(np.abs(xyz)*65536+.5)).astype(np.int32)
        rgb=self.colors.astype(np.int32)
        rows[:len(rgb),3]=(rgb[:,0]<<16)|(rgb[:,1]<<8)|rgb[:,2]
        rows[len(rgb):,3]=0xffc440
        return rows.tobytes()


def write_geometry(stream,session,epoch,sequence,geometry):
    if not isinstance(geometry,GeometryFrame):raise ValueError('expected owned geometry')
    raw=geometry.packed()
    meta=dict(session=session,epoch=epoch,sequence=sequence,length=len(raw),kind='geometry',schema=1,
              point_count=len(geometry.points),trajectory_count=len(geometry.trajectory),
              units=geometry.units,frame_id=geometry.frame_id,metric_verified=geometry.metric_verified)
    _frame_meta(meta);write_json(stream,meta);stream.write(raw);stream.flush()


def decode_geometry(meta,raw):
    _frame_meta(meta)
    count,trail=meta.get('point_count'),meta.get('trajectory_count')
    if (meta.get('kind')!='geometry' or meta.get('schema')!=1 or type(count) is not int
            or type(trail) is not int or not 0<=count<=65536 or not 0<=trail<=1024
            or meta['length']!=(count+trail)*16 or len(raw)!=meta['length']):
        raise ValueError('geometry envelope size/count mismatch')
    words=np.frombuffer(raw,dtype='<i4').reshape(-1,4)
    if np.any(words[:,3]<0) or np.any(words[:,3]>0xffffff):raise ValueError('geometry packed RGB')
    rgb=np.stack(((words[:count,3]>>16)&255,(words[:count,3]>>8)&255,words[:count,3]&255),axis=1).astype(np.uint8)
    return GeometryFrame(words[:count,:3].astype(np.float64)/65536,rgb,
        trajectory=words[count:,:3].astype(np.float64)/65536,units=meta.get('units'),
        frame_id=meta.get('frame_id'),metric_verified=meta.get('metric_verified'))


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
