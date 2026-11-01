"""Native display scan adapter; no PL loading or motor output."""
import ctypes as C
import os
import time
import threading

import numpy as np
from ssvep_hdmi import SCAN_PERIOD, ScanEvidence, pattern
from system_hdmi import FREQUENCY_BOXES

MAX_ROWS=3000
ERRORS=('ok','invalid_native_configuration','scheduler_admission_failed','buffer_owner_changed',
        'dma_fault_or_halt','frame_did_not_latch','scan_deadline_missed','copy_missed_next_scan',
        'late_latch_acknowledgement','cache_sync_failed','controlled_stop',
        'record_capacity_exhausted','scan_cpu_budget_exceeded','producer_heartbeat_expired')


class Frame(C.Structure):
    _fields_=[('data',C.c_void_p),('bo',C.c_uint32),('coherent',C.c_uint32),('offset',C.c_size_t)]


class Corner(C.Structure):
    _fields_=[(key,C.c_uint32) for key in ('x','y','width','height')]+[
        (key,C.c_void_p) for key in ('off','on','chosen_off','chosen_on')]


class Feedback(C.Structure):
    _fields_=[(key,C.c_uint32) for key in ('x','y','width','height')]+[
        ('states',C.c_void_p),('count',C.c_uint32)]


class Config(C.Structure):
    _fields_=[(key,C.c_void_p) for key in ('counter','index','status','park','sync','software_clock','device')]+[
        ('frames',Frame*3),('corners',Corner*4),('masks',C.c_void_p),
        ('mask_count',C.c_uint32),('initial_mask',C.c_uint32),
        ('duration_ns',C.c_uint64),('period_ns',C.c_uint64),('realtime',C.c_int),('cpu',C.c_int),
        ('base',C.c_void_p),('initialized_mask',C.c_uint32),
        ('require_heartbeat',C.c_uint32),('heartbeat_ms',C.c_uint32),('feedback',Feedback)]


class Receipt(C.Structure):
    _fields_=[(key,C.c_uint32) for key in ('before','after','target','requested','active','mask','status','reserved')]+[
        (key,C.c_uint64) for key in ('ack_ns','park_ns','copy_ns','flush_ns','copied_bytes','flushed_bytes')]


class Outcome(C.Structure):
    _fields_=[(key,C.c_uint32) for key in ('error','count','origin','initial_index','end_counter','end_index',
        'policy','priority','cpu','scheduler_errno')]+[
        (key,C.c_uint64) for key in ('onset_ns','end_ns','last_copy_ns','last_flush_ns',
                                   'worker_cpu_ns','max_cycle_cpu_ns')]


def pointer(function):
    return C.cast(function,C.c_void_p).value


class NativeOwnershipError(RuntimeError):
    def __init__(self,worker):
        super().__init__('Native scan did not stop; retain display buffers')
        self.worker=worker


class NativeScan:
    def __init__(self,path):
        self.lib=C.CDLL(str(path),use_errno=True)
        for name,structure in (('config',Config),('receipt',Receipt),('outcome',Outcome)):
            size=getattr(self.lib,'gl_scan_'+name+'_size')
            size.restype=C.c_size_t
            if size()!=C.sizeof(structure):raise RuntimeError('Native scan ABI differs: '+name)
        self.lib.gl_scan_start.argtypes=[C.POINTER(Config)]
        self.lib.gl_scan_start.restype=C.c_void_p
        self.lib.gl_scan_validate.argtypes=[C.POINTER(Config)]
        self.lib.gl_scan_validate.restype=C.c_int
        self.lib.gl_scan_done.argtypes=[C.c_void_p]
        self.lib.gl_scan_done.restype=C.c_int
        self.lib.gl_scan_cancel.argtypes=[C.c_void_p]
        self.lib.gl_scan_cancel.restype=None
        self.lib.gl_scan_collect.argtypes=[C.c_void_p,C.POINTER(Outcome),C.POINTER(Receipt),C.c_uint32]
        self.lib.gl_scan_collect.restype=C.c_int
        self.lib.gl_scan_read.argtypes=[C.c_void_p,C.c_uint32,C.POINTER(Outcome),C.POINTER(Receipt),C.c_uint32]
        self.lib.gl_scan_read.restype=C.c_int
        self.lib.gl_scan_touch.argtypes=[C.c_void_p,C.c_uint32]
        self.lib.gl_scan_touch.restype=None
        self.lib.gl_scan_select.argtypes=[C.c_void_p,C.c_int]
        self.lib.gl_scan_select.restype=C.c_int
        self.lib.gl_scan_feedback.argtypes=[C.c_void_p,C.c_uint32]
        self.lib.gl_scan_feedback.restype=C.c_int
        self.lib.gl_scan_bind_vdma.argtypes=[C.c_void_p,C.c_void_p]
        self.lib.gl_scan_bind_vdma.restype=C.c_int
        self.lib.gl_scan_request_park.argtypes=[C.c_uint]
        self.lib.gl_scan_request_park.restype=C.c_int
        self.session=None
        self.owners=None
        self.lock=threading.Lock()

    def bind_display_park(self,display):
        if not self.lib.gl_scan_bind_vdma(pointer(display.Xil_In32),pointer(display.Xil_Out32)):
            raise ValueError('Native VDMA request binding failed')
        return pointer(self.lib.gl_scan_request_park)

    def start(self,config,owners):
        with self.lock:
            if self.session:raise RuntimeError('Native scan already owns buffers')
            self.owners=(config,owners)
            self.session=self.lib.gl_scan_start(C.byref(config))
            if not self.session:
                self.owners=None
                raise OSError(C.get_errno(),'Native scan admission failed')

    def done(self):
        with self.lock:
            return self.session is None or bool(self.lib.gl_scan_done(self.session))

    def cancel(self):
        with self.lock:
            if self.session:self.lib.gl_scan_cancel(self.session)

    def touch(self,stamp):
        with self.lock:
            if self.session:self.lib.gl_scan_touch(self.session,int(stamp*1000)&0xffffffff)

    def select(self,selected):
        if selected not in (None,8,10,12,14):raise ValueError('Invalid selected frequency')
        with self.lock:
            if self.session and not self.lib.gl_scan_select(self.session,
                    -1 if selected is None else (8,10,12,14).index(selected)):
                raise ValueError('Native selection rejected')

    def read(self,cursor):
        result=Outcome();rows=(Receipt*8)()
        with self.lock:
            if not self.session:raise RuntimeError('Native scan session closed')
            count=self.lib.gl_scan_read(self.session,cursor,C.byref(result),rows,8)
            done=bool(self.lib.gl_scan_done(self.session))
            if done and not result.end_ns:
                count=self.lib.gl_scan_read(self.session,cursor,C.byref(result),rows,8)
        if count<0:raise ValueError('Invalid native receipt cursor')
        return result,list(rows[:count]),done

    def feedback(self,index):
        with self.lock:
            if self.session and not self.lib.gl_scan_feedback(self.session,index):
                raise ValueError('Native feedback state rejected')

    def stop(self):
        self.cancel()
        deadline=time.monotonic()+1.2
        while not self.done():
            if time.monotonic()>deadline:
                raise NativeOwnershipError(self)
            time.sleep(.01)

    def collect(self):
        result=Outcome();rows=(Receipt*MAX_ROWS)()
        with self.lock:
            if not self.session or not self.lib.gl_scan_collect(self.session,C.byref(result),rows,MAX_ROWS):
                raise RuntimeError('Native scan still owns buffers')
            self.session=None;self.owners=None
        return result,rows


def hardware_config(display,frames,buffers,seconds):
    from pynq._3rdparty import xrt
    if (len(buffers)!=3 or not 5<=seconds<=45
            or xrt.libc._name!='/usr/lib/libxrt_core.so'
            or int(xrt.xclBOSyncDirection.XCL_BO_SYNC_BO_TO_DEVICE)!=0):
        raise ValueError('Unverified native scan hardware ABI')
    config=Config()
    for name,symbol in (('counter','display_frames'),('index','display_index'),
                        ('status','display_status'),('park','display_park')):
        setattr(config,name,pointer(getattr(display,symbol)))
    config.sync=pointer(xrt.libc.xclSyncBO)
    # Installed PYNQ xclOpen returns LP_c_void_p, but the native XRT ABI is void*.
    # Preserve the pointer value; do not dereference this opaque handle.
    config.device=C.cast(buffers[0].device.handle,C.c_void_p)
    if not config.device:raise ValueError('Native scan device handle is null')
    for i,buffer in enumerate(buffers):
        if (buffer.shape!=(720,1280,3) or buffer.dtype!=np.uint8 or not buffer.flags.c_contiguous
                or buffer.device is not buffers[0].device or buffer.offset!=0):
            raise ValueError('Native scan requires complete shared CMA frames')
        config.frames[i]=Frame(buffer.ctypes.data,buffer.bo,int(buffer.coherent),buffer.offset)
    for i,(hz,_,box) in enumerate(FREQUENCY_BOXES):
        x,y,x1,y1=box
        patches=[frames.patches[(hz,state,chosen)] for chosen in (False,True) for state in (False,True)]
        if any(not patch.flags.c_contiguous for patch in patches):
            raise ValueError('Native scan corner patch is not contiguous')
        config.corners[i]=Corner(x,y,x1-x+1,y1-y+1,*(patch.ctypes.data for patch in patches))
    masks=np.asarray([pattern(n) for n in range(MAX_ROWS)],dtype=np.uint8)
    config.masks=masks.ctypes.data;config.mask_count=MAX_ROWS;config.initial_mask=pattern(0)
    config.duration_ns=round(seconds*1e9);config.period_ns=round(SCAN_PERIOD*1e9)
    config.realtime=1;config.cpu=1
    config.initialized_mask=7
    return config,(display,xrt.libc,frames,buffers,masks)


def receipt_dict(record):
    return dict(counter_before=record.before,counter_after=record.after,target_counter=record.target,
                requested_index=record.requested,active_index=record.active,pattern_mask=record.mask,
                dma_status=record.status,ack_monotonic=record.ack_ns/1e9)


class NativeStimulusScan:
    """Prepare inactive menu buffers, then stream immutable native latch receipts."""
    def __init__(self,library,display,frames,buffers):
        self.worker=NativeScan(library)
        self.config,self.owners=hardware_config(display,frames,buffers,30)
        self.config.park=self.worker.bind_display_park(display)
        active=display.display_index()
        if active not in (0,1,2):raise ValueError('Invalid active HDMI buffer')
        self.config.initialized_mask=7^(1<<active)
        self.config.base=frames.base.ctypes.data
        self.config.feedback=Feedback(*frames.feedback_box,frames.feedback_patches.ctypes.data,
                                      len(frames.feedback_states))
        if not frames.base.flags.c_contiguous:raise ValueError('Noncontiguous stimulus shell')
        for index,buffer in enumerate(buffers):
            if index==active:continue
            if display.display_index()!=active:raise ValueError('HDMI owner changed during preparation')
            frames.paint(buffer,index,pattern(0))
        self.config.require_heartbeat=1
        self.cursor=0

    def begin(self):
        self.config.heartbeat_ms=int(time.monotonic()*1000)&0xffffffff
        self.worker.start(self.config,self.owners)
        deadline=time.monotonic()+.2
        while True:
            result,_,done=self.worker.read(0)
            if done:raise ValueError('Native scan ended during onset: '+ERRORS[result.error])
            if result.onset_ns:
                return dict(origin_counter=result.origin,active_index=result.initial_index,
                            presented_monotonic=result.onset_ns/1e9)
            if time.monotonic()>deadline:raise ValueError('Native onset timeout')
            time.sleep(.002)

    def read(self):
        result,records,done=self.worker.read(self.cursor)
        if done:raise ValueError('Native scan ended: '+ERRORS[result.error])
        self.cursor+=len(records)
        return [receipt_dict(record) for record in records]

    def touch(self,stamp):self.worker.touch(stamp)
    def select(self,selected):self.worker.select(selected)
    def feedback(self,index):self.worker.feedback(index)
    def cancel(self):self.worker.cancel()
    def close(self):
        self.worker.stop()
        if self.worker.session:return self.worker.collect()[0]


def preflight(display,frames,buffers,seconds,library):
    """Verify real CMA/XRT without calling any display function or starting a worker."""
    config,owners=hardware_config(display,frames,buffers,seconds)
    scan=NativeScan(library)
    if not scan.lib.gl_scan_validate(C.byref(config)):
        raise ValueError('Native scan configuration failed before PL loading')
    sync=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint,C.c_int,C.c_size_t,C.c_size_t)(config.sync)
    checks=0
    for i,buffer in enumerate(buffers):
        if not buffer.coherent:
            if sync(config.device,buffer.bo,0,buffer.nbytes,buffer.offset):
                raise RuntimeError('Native cache-sync ABI failed before PL loading')
            checks+=1
    return dict(config_valid=True,cache_sync_checks=checks,display_functions_called=False,
                worker_started=False,device_handle_type=type(buffers[0].device.handle).__name__,
                opaque_pointer_preserved=True)


def measurement(result,records,main_policy=None):
    origin=dict(origin_counter=result.origin,active_index=result.initial_index,
                presented_monotonic=result.onset_ns/1e9)
    rows=[];rejected=None;consumer_error=None
    evidence=ScanEvidence(**dict(origin=result.origin,onset=result.onset_ns/1e9,
                               buffer_index=result.initial_index)) if result.onset_ns else None
    for record in records[:result.count]:
        row=dict(counter_before=record.before,counter_after=record.after,target_counter=record.target,
                 requested_index=record.requested,active_index=record.active,pattern_mask=record.mask,
                 dma_status=record.status,ack_monotonic=record.ack_ns/1e9)
        try:evidence.observe([row],row['ack_monotonic'])
        except ValueError as error:
            consumer_error=str(error);rejected=row;break
        rows.append(row)
    inflight=records[min(result.count,MAX_ROWS-1)]
    if result.error and inflight.ack_ns:
        rejected={key:getattr(inflight,key) for key,_ in Receipt._fields_}
    error=ERRORS[result.error] if result.error else consumer_error
    elapsed=(result.end_ns-result.onset_ns)/1e9 if result.onset_ns else 0.
    timings={}
    for label,field in (('park_ack_ms','park_ns'),('copy_ms','copy_ns'),('flush_ms','flush_ns')):
        values=[getattr(row,field)/1e6 for row in records[:result.count]]
        timings[label]=values
        if values:timings[label+'_summary']=dict(median=float(np.median(values)),
            p95=float(np.percentile(values,95)),maximum=max(values))
    return dict(scope='fixed_brightness_native_scan_only',optical_measurement=False,
        visible_stimulus_tested=False,completed=not error,error=error,elapsed_s=elapsed,
        origin=origin,latches=rows,rejected_latch=rejected,verified_single_scan_latches=len(rows),
        native_error_code=result.error,consumer_error=consumer_error,
        validation='unchanged_ScanEvidence_offline_recheck_no_live_direction',
        scan_evidence=evidence.snapshot(rows[-1]['ack_monotonic']) if rows else None,
        scheduler=dict(worker_policy=result.policy,worker_priority=result.priority,
                       worker_cpu=result.cpu,scheduler_errno=result.scheduler_errno,
                       scan_cpu_budget_ms=8,main_thread_policy=main_policy,
                       worker_cpu_ms=result.worker_cpu_ns/1e6,
                       max_cycle_cpu_ms=result.max_cycle_cpu_ns/1e6),
        last_copy_ms=result.last_copy_ns/1e6,last_flush_ms=result.last_flush_ns/1e6,
        counter=result.end_counter,active_index=result.end_index,**timings)


def measure_native(display,frames,buffers,seconds,library):
    main_policy=os.sched_getscheduler(0)
    if main_policy!=os.SCHED_OTHER:
        raise RuntimeError('Native probe requires ordinary main-thread scheduling')
    config,owners=hardware_config(display,frames,buffers,seconds)
    worker=NativeScan(library)
    worker.start(config,owners)
    try:
        deadline=time.monotonic()+seconds+2
        while not worker.done():
            if time.monotonic()>deadline:raise RuntimeError('Native scan wall-time limit exceeded')
            time.sleep(.05)
    except BaseException:
        worker.stop()
        worker.collect()
        raise
    worker.stop()
    report=measurement(*worker.collect(),main_policy=main_policy)
    report['scheduler']['main_thread_policy_after']=os.sched_getscheduler(0)
    if report['scheduler']['main_thread_policy_after']!=main_policy:
        raise RuntimeError('Native probe changed main-thread scheduling')
    return report
