"""Fixed-brightness integration diagnostic; never decode EEG or emit directions."""
import threading
import time

from hdmi_stimulus import HdmiStimulus
from native_scan import NativeOwnershipError, NativeStimulusScan
from ssvep_hdmi import POLICY, ScanEvidence


class DiagnosticBridge:
    """Validate real display receipts only. This is not an acquisition backend."""
    def __init__(self):
        self.lock=threading.Lock();self.sessions=[];self.current=None

    def hdmi_command(self,command):
        with self.lock:
            action=command['action']
            if action=='start':
                self.current=dict(id='display-diagnostic-'+str(len(self.sessions)+1),
                    page=command['page_id'],origin=None,evidence=None,latches=[],stopped=False)
                self.sessions.append(self.current)
            row=self.current
            if row is None:raise ValueError('Diagnostic session missing')
            if action!='start' and (command['id']!=row['id'] or command['page_id']!=row['page']):
                raise ValueError('Diagnostic page/session changed')
            if action=='presented':
                row['origin']={k:command[k] for k in
                    ('origin_counter','active_index','presented_monotonic')}
                row['evidence']=ScanEvidence(command['origin_counter'],
                    command['presented_monotonic'],command['active_index'])
            elif action=='heartbeat':
                if row['evidence'] is None or row['stopped']:raise ValueError('No active diagnostic presentation')
                row['evidence'].observe(command['latches'],time.monotonic())
                row['latches'].extend(command['latches'])
            elif action=='stop':row['stopped']=True
            return dict(id=row['id'],policy=POLICY,display_page_id=row['page'],
                state='awaiting_presentation' if action=='start' else 'active',
                source='display_diagnostic_not_eeg',control_enabled=False,
                display_timing=row['evidence'].snapshot(time.monotonic()) if row['evidence'] else None)

    def snapshot(self):
        with self.lock:
            return [{k:v for k,v in row.items() if k!='evidence'} for row in self.sessions]


def measure_integrated(lib,frames,buffers,view,library,seconds):
    if seconds!=30:raise ValueError('Integration diagnostic is limited to 30 seconds')
    bridge=DiagnosticBridge();native_results=[];events=[]
    class RecordedScan(NativeStimulusScan):
        def close(self):
            result=super().close()
            if result is not None:
                native_results.append({k:getattr(result,k) for k in
                    ('error','count','policy','priority','cpu','worker_cpu_ns','max_cycle_cpu_ns')})
            return result
    lane=HdmiStimulus(lib,buffers,view,bridge,native_library=library,
                      scan_factory=RecordedScan,frames=frames)
    controller=view.controller
    started=time.monotonic();error=None
    def healthy():
        if lane.error:raise ValueError(lane.error)
        if not lane.active or lane.ended.is_set():raise ValueError('Diagnostic lane stopped unexpectedly')
    def run_until(offset):
        while time.monotonic()-started<offset:
            healthy();lane.service(controller,time.monotonic());time.sleep(.005)
    def enter():
        controller._enter('drive',time.monotonic())
        lane.start(controller.page_id,consent=True)
        events.append(dict(action='entered',page_id=controller.page_id,elapsed_s=time.monotonic()-started))
    def exit_page(action):
        healthy()
        row=lane.input(controller.page_id,time.monotonic())
        if not row or row[0]['display_timing']['ready'] is not True:
            raise ValueError('Diagnostic timing never became ready')
        if action=='force_stop':controller.force_stop(time.monotonic())
        else:controller._enter('home',time.monotonic())
        lane.service(controller,time.monotonic())
        if lane.active or lane.input(controller.page_id,time.monotonic()) is not None:
            raise ValueError('Old diagnostic evidence survived exit')
        if controller.direction!='stop':raise ValueError('Diagnostic direction was not stopped')
        target=(lib.display_index()+1)%3
        view.compose(buffers[target],target,now=time.monotonic())
        buffers[target].flush()
        if not lib.display_park(target):raise ValueError('Return menu failed to latch')
        events.append(dict(action=action,page_id=controller.page_id,evidence_revoked=True,
                           native_joined=True,elapsed_s=time.monotonic()-started))
    try:
        enter();run_until(8);exit_page('page_exit');time.sleep(max(0,9-(time.monotonic()-started)))
        enter();run_until(17);exit_page('force_stop');time.sleep(max(0,18-(time.monotonic()-started)))
        enter();run_until(30)
        lane.stop()
        if lane.input(controller.page_id,time.monotonic()) is not None:
            raise ValueError('Final stop left readable evidence')
        events.append(dict(action='final_stop',evidence_revoked=True,native_joined=True,
                           elapsed_s=time.monotonic()-started))
        if any(row['error'] not in (0,10) for row in native_results):
            raise ValueError('Native diagnostic scan failed')
    except (OSError,ValueError,RuntimeError) as exc:
        error=str(exc)
    finally:
        try:lane.close()
        except Exception as exc:
            # Keep the complete lane, mappings and CMA alive until independent recovery.
            raise NativeOwnershipError(lane) from exc
    sessions=bridge.snapshot()
    return dict(scope='fixed_brightness_native_live_adapter_navigation_only',
        visible_stimulus_tested=False,optical_measurement=False,eeg_session_started=False,
        phone_stop_transport_tested=False,physical_output_enabled=False,
        elapsed_s=time.monotonic()-started,completed=error is None,error=error,
        events=events,sessions=sessions,native_results=native_results,
        verified_single_scan_latches=sum(len(row['latches']) for row in sessions))
