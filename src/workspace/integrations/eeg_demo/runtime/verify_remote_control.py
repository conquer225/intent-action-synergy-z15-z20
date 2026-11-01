"""Disconnected-motor regression through the deployed phone API and ESP receiver."""
import argparse
import json
import os
from pathlib import Path
import signal
import threading
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler,Request,build_opener

BASE=Path('/home/xilinx/gl-hdmi-live-20261008-ea117349')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--motor-power-disconnected',action='store_true',required=True)
    p.add_argument('--sustain-seconds',type=float,default=3.)
    p.add_argument('--require-gpio-readback',action='store_true')
    args=p.parse_args()
    if not args.motor_power_disconnected:raise ValueError('Disconnect motor power before this regression')
    if not 3<=args.sustain_seconds<=30:raise ValueError('Regression duration must be 3 to 30 seconds')
    opener=build_opener(ProxyHandler({}));key=(BASE/'access.key').read_text().strip()
    result=dict(motor_power_disconnected_reported=True,physical_wheel_observation=False,checks=[])

    def api(body=None):
        request=Request('http://127.0.0.1:9119/api/player',
            data=json.dumps(body).encode() if body is not None else None,
            headers={'X-Media-Key':key,'Origin':'http://127.0.0.1:9119','Content-Type':'application/json'})
        with opener.open(request,timeout=3) as response:return json.load(response)

    first=api();receiver=first['wheelchair']['receiver_url']
    def status():
        with opener.open(receiver+'/api/status',timeout=1) as response:return json.load(response)

    def stopped():
        state=status()
        assert state['requested_direction']=='stop' and not state['armed'] and not state['manual_active'],state
        if args.require_gpio_readback:check_gpio(state,'stop')
        return state

    def check_gpio(state,direction):
        expected={'stop':'0000','forward':'0011','backward':'1100','left':'1001','right':'0110'}[direction]
        assert state.get('gpio_profile')=='input_output_v1',state
        assert state.get('gpio_readback_available') is True and state.get('gpio_pin_order')==[10,11,12,13],state
        assert state.get('requested_direction')==direction,state
        assert state.get('gpio_requested_bits')==expected and state.get('gpio_input_bits')==expected,state
        return dict(direction=direction,expected=expected,requested=state['gpio_requested_bits'],input_bits=state['gpio_input_bits'])

    def wait_stop():
        start=time.monotonic()
        while status()['requested_direction']!='stop':
            assert time.monotonic()-start<1.6,'Stop did not revoke output'
            time.sleep(.05)
        stopped()
        return time.monotonic()-start

    def choose(direction):
        epoch=api()['wheelchair_control_epoch']
        return api(dict(action='wheelchair_manual',value=dict(direction=direction,epoch=epoch)))['command_id']

    def heartbeat(identifier):return api(dict(action='wheelchair_heartbeat',value=identifier))

    phone=dict(id=None,error=None,count=0,gap_max=0.)
    done=threading.Event()
    def foreground_phone():
        previous=None
        while not done.wait(.2):
            identifier=phone['id']
            if identifier is None:previous=None;continue
            try:
                heartbeat(identifier)
                now=time.monotonic();phone['count']+=1
                if previous is not None:phone['gap_max']=max(phone['gap_max'],now-previous)
                previous=now
            except (HTTPError,OSError,ValueError) as error:
                if identifier==phone['id']:phone.update(id=None,error=repr(error))
    thread=threading.Thread(target=foreground_phone,daemon=True);thread.start()

    def run_motion(direction,seconds):
        phone.update(id=None,error=None)
        identifier=choose(direction);start=time.monotonic();seen=False;observations=0
        phone['id']=identifier
        next_ui=start
        while time.monotonic()-start<seconds:
            sender=Path('/dev/shm')/(BASE.name+'-wheelchair-link.json')
            row=json.loads(sender.read_text())
            if time.monotonic()>=next_ui:api();next_ui=time.monotonic()+1
            assert phone['error'] is None,phone
            if row.get('command_id')==identifier and row.get('direction')==direction and row.get('sent') is True:
                seen=True;observations+=1
            elif seen:raise AssertionError('Movement stopped: '+json.dumps(dict(phone=phone,sender=row)))
            time.sleep(.16)
        assert seen,'Direction never acknowledged'
        if args.require_gpio_readback:
            result['checks'].append(dict(test='gpio_input_readback',**check_gpio(status(),direction)))
        result['checks'].append(dict(test='continuous_'+direction,seconds=time.monotonic()-start,observations=observations))
        return identifier

    paused=None
    try:
        initial=stopped()
        assert initial['firmware']=='guardianloop-wheelchair-remote-0.1.0'
        assert initial['motor_gpio_enabled'] is True and initial['manual_lease_ms']==500
        run_motion('forward',args.sustain_seconds)
        run_motion('backward',2)
        phone['id']=None;api(dict(action='wheelchair_manual',value='stop'))
        result['checks'].append(dict(test='explicit_phone_stop',observed_within_seconds=wait_stop()))

        identifier=run_motion('left',1.5)
        phone['id']=None
        result['checks'].append(dict(test='phone_heartbeat_loss',observed_within_seconds=wait_stop()))
        try:heartbeat(identifier)
        except HTTPError as error:assert error.code==409
        else:raise AssertionError('Expired heartbeat revived an old command')
        time.sleep(.3);stopped()

        identifier=run_motion('right',1.5)
        output=Path('/dev/shm')/(BASE.name+'-wheelchair-link.json')
        assert json.loads(output.read_text())['direction']=='right'
        candidates=[]
        for entry in Path('/proc').iterdir():
            if entry.name.isdecimal():
                try:command=(entry/'cmdline').read_bytes().split(b'\0')
                except (FileNotFoundError,ProcessLookupError):continue
                if str(BASE/'wheelchair_link.py').encode() in command:candidates.append(int(entry.name))
        assert len(candidates)==1,candidates
        paused=candidates[0];os.kill(paused,signal.SIGSTOP)
        start=time.monotonic()
        time.sleep(.65)
        stopped()
        result['checks'].append(dict(test='sender_paused_receiver_deadman',observed_within_seconds=time.monotonic()-start))
        os.kill(paused,signal.SIGCONT);paused=None
        time.sleep(.3);stopped()
        result['checks'].append(dict(test='sender_resumed_does_not_rearm',passed=True))
        result['passed']=True
    except BaseException as error:
        result.update(passed=False,error=repr(error));raise
    finally:
        phone['id']=None;done.set();thread.join(timeout=3)
        if paused is not None:os.kill(paused,signal.SIGCONT)
        api(dict(action='wheelchair_manual',value='stop'))
        time.sleep(.4)
        result['final']=status()
        result['phone']=phone
        (Path(__file__).resolve().parent/'last-regression.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result),flush=True)


if __name__=='__main__':main()
