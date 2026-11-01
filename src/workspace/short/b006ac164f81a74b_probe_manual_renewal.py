"""Trace receiver HTTP lease renewals with motor power disconnected; no retries."""
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler,build_opener

from bench_network_bridge import BenchReceiver,ReceiverError,load_config


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--motor-power-disconnected',action='store_true',required=True)
    p.parse_args()
    url,key=load_config(Path('/home/xilinx/wheelchair_virtual_20261006/receiver_private.json'))
    receiver=BenchReceiver(url,key,motor_test=True)
    opener=build_opener(ProxyHandler({}));trace=[]
    class Trace:
        def open(self,request,timeout):
            start=time.monotonic()
            try:
                response=opener.open(request,timeout=timeout)
                trace.append(dict(path=request.selector,start=start,seconds=time.monotonic()-start,code=response.status))
                return response
            except HTTPError as error:
                trace.append(dict(path=request.selector,start=start,seconds=time.monotonic()-start,code=error.code,
                                  reply=error.read(1024).decode(errors='replace')))
                raise
    receiver.opener=Trace();result={}
    try:
        receiver.stop();time.sleep(.4)
        boot=receiver.begin_manual();start=time.monotonic();count=0
        while time.monotonic()-start<10:
            row=receiver.send_direction('forward',manual_boot=boot)
            if not row['sent']:raise AssertionError(row)
            count+=1;time.sleep(.1)
        result.update(passed=True,renewals=count)
    except (ReceiverError,AssertionError,OSError,ValueError) as error:result.update(passed=False,error=repr(error))
    finally:
        receiver.stop();result['trace']=trace
        (Path(__file__).resolve().parent/'renewal-trace.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result),flush=True)


if __name__=='__main__':main()
