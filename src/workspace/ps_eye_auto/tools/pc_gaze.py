"""PC adapter: firmware localization and gaze C, with monotonic host timing."""
import ctypes as C
import hashlib
import json
import time
from pc_model import ROOT,Detector,Roi,Box,Loc,np,cv2
from build_pc_gaze import FIELDS

DIRECTIONS={0:'INVALID',1:'LEFT',2:'CENTER',3:'RIGHT'}
REASONS={0:'ok',1:'pair_lost',2:'position_changed',3:'too_slow',4:'cal_failed',5:'cal_started',6:'reset'}

def calibration_diagnostic(state):
    eye={1:'画面左眼',2:'画面右眼'}.get(state['cal_failure_eye'],'眼部')
    stage={1:'左',2:'中',3:'右'}.get(state['cal_retry_stage'],'当前')
    reason=state['cal_failure_reason'];gap=state['cal_failure_gap'];noise=state['cal_failure_noise']
    detail={1:f'相邻点间距 {gap}，需要至少 6',2:'中点不在左右参考之间',
            3:f'相邻点间距 {gap}，未超过抖动门槛 {noise}'}.get(reason,'采样未通过')
    return f'校准未通过：{eye}{detail}。点击“重采失败点”从{stage}点继续；换坐姿请先清除校准。'
FEATURE_REASONS={0:'等待稳定帧',1:'暗部有效',2:'眼框越界或过小',3:'局部对比度不足',
                 4:'暗区比例异常',5:'未找到集中暗部',6:'多个暗部或噪声干扰'}
TRACKING_REASONS={0:'等待新鲜样本',1:'方向稳定',2:'眼部暂失',3:'超出个人校准范围',
                  4:'双眼方向冲突',5:'位于方向边界',6:'等待方向切换确认',7:'采样间隔过长'}

def eye_diagnostic(state,eye):
    samples=state[eye+'_samples'];dark=state[eye+'_dark'];selected=state[eye+'_selected']
    metrics='' if not samples else f" · 暗区 {dark*100/samples:.0f}% / 主暗部 {selected*100/samples:.0f}% · 对比 {state[eye+'_contrast']} · 阈值 {state[eye+'_threshold']}"
    return FEATURE_REASONS.get(state[eye+'_reason'],'未知状态')+metrics

def check_gaze_files():
    dll=ROOT/'pc_runtime/gaze.dll'
    manifest=json.loads((ROOT/'pc_runtime/gaze_manifest.json').read_text(encoding='utf-8'))
    if C.sizeof(C.c_void_p)!=8:raise RuntimeError('请使用 64 位 Python。')
    if manifest['abi']!=1 or manifest['fields']!=FIELDS or hashlib.sha256(dll.read_bytes()).hexdigest()!=manifest['dll_sha256']:
        raise RuntimeError('眼动 DLL 与记录不一致，请运行 tools/build_pc_gaze.py 重建。')
    for name,digest in manifest['sources'].items():
        if hashlib.sha256((ROOT/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=digest:
            raise RuntimeError('算法源码已改变，请运行 tools/build_pc_gaze.py 重建：'+name)
    return dll

class GazeEngine(Detector):
    def __init__(self):
        self.lib=C.CDLL(str(check_gaze_files()))
        self.lib.pc_abi_value.argtypes=[C.c_uint];self.lib.pc_abi_value.restype=C.c_uint
        expected=[C.sizeof(Roi),C.sizeof(Box),C.sizeof(Loc)]+[getattr(Loc,n).offset for n,_ in Loc._fields_]
        if [self.lib.pc_abi_value(i) for i in range(len(expected))]!=expected:
            raise RuntimeError('定位 ABI 不匹配。')
        self.lib.auto_localize.argtypes=[C.c_void_p,C.c_uint32,C.c_uint32,C.c_uint32,C.POINTER(Loc)]
        self.lib.auto_localize.restype=C.c_int
        self.lib.pc_gaze_create.argtypes=[];self.lib.pc_gaze_create.restype=C.c_void_p
        for name in ('destroy','reset'):
            fn=getattr(self.lib,'pc_gaze_'+name);fn.argtypes=[C.c_void_p];fn.restype=None
        self.lib.pc_gaze_calibrate.argtypes=[C.c_void_p];self.lib.pc_gaze_calibrate.restype=C.c_int
        self.lib.pc_gaze_retry.argtypes=[C.c_void_p];self.lib.pc_gaze_retry.restype=C.c_int
        self.lib.pc_gaze_values.argtypes=[C.c_void_p,C.POINTER(C.c_uint32),C.c_uint]
        self.lib.pc_gaze_values.restype=C.c_uint
        self.lib.pc_gaze_step.argtypes=[C.c_void_p,C.c_void_p,C.c_uint32,C.c_uint32,C.c_uint32,C.POINTER(Loc),C.c_uint32,C.c_uint32]
        self.lib.pc_gaze_step.restype=None
        self.context=self.lib.pc_gaze_create()
        if not self.context:raise MemoryError('无法分配眼动状态。')
        self.last_sample=None
        if self.lib.pc_gaze_values(self.context,None,0)!=len(FIELDS):
            self.close();raise RuntimeError('眼动 ABI 不匹配。')

    def state(self):
        if not self.context:raise RuntimeError('眼动会话已关闭。')
        values=(C.c_uint32*len(FIELDS))()
        self.lib.pc_gaze_values(self.context,values,len(values))
        state=dict(zip(FIELDS,values))
        state['direction_name']=DIRECTIONS[state['direction']]
        state['reason_name']=REASONS[state['reason']]
        state['tracking_name']=TRACKING_REASONS[state['tracking_reason']]
        state['gaze_raw']=state['gaze_raw_offset']-512
        state['gaze_filtered']=state['gaze_filtered_offset']-512
        return state

    def reset(self):
        self.lib.pc_gaze_reset(self.context)
        return self.state()

    def calibrate(self,now=None,retry=False):
        now=time.monotonic() if now is None else now
        if self.last_sample is None or not 0<=now-self.last_sample<=1:
            return False
        fn=self.lib.pc_gaze_retry if retry else self.lib.pc_gaze_calibrate
        return bool(fn(self.context))

    def process(self,frame,sampled=None):
        sampled=time.monotonic() if sampled is None else sampled
        frame=np.ascontiguousarray(frame)
        result=self.detect(frame)  # Inherited real firmware Haar implementation.
        loc=Loc()
        loc.face=Box(*result['face'],int(result['valid']))
        loc.left=Roi(*result['left'],24,80);loc.right=Roi(*result['right'],24,80)
        loc.valid=int(result['valid']);loc.faces=result['faces'];loc.eye_count=result['eye_count']
        dt=0 if self.last_sample is None else max(0,int((sampled-self.last_sample)*1000))
        self.last_sample=sampled
        with self.lock:
            self.lib.pc_gaze_step(self.context,frame.ctypes.data,frame.strides[0],
                                 frame.shape[1],frame.shape[0],C.byref(loc),min(dt,0xffffffff),int(result['host_ms']))
            state=self.state()
        return dict(**result,gaze=state,period_ms=dt,sampled=sampled)

    def close(self):
        if getattr(self,'context',None):
            self.lib.pc_gaze_destroy(self.context);self.context=None

def annotate_gaze(frame,result):
    output=frame.copy();s=result['gaze']
    if result['valid']:
        x,y,w,h=result['face'];cv2.rectangle(output,(x,y),(x+w-1,y+h-1),(0,210,255),2)
        for eye,prefix in [('left','l'),('right','r')]:
            x,y,w,h=[s[prefix+n] for n in ('x','y','w','h')]
            good=s[eye+'_valid']
            cv2.rectangle(output,(x,y),(x+w-1,y+h-1),(40,220,80) if good else (60,60,240),2)
            if good:cv2.drawMarker(output,(s[eye+'_x'],s[eye+'_y']),(40,220,80),cv2.MARKER_CROSS,12,1)
    return output
