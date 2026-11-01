"""Bounded, observation-only TCP v1 handshake and heartbeat check."""
import argparse
import json
import socket
import time


def probe(host,port=9000,duration=3):
    result={'passed':False,'host':host,'port':port,'source':'eye','acks':0,'telemetry':0,'rtt_ms':[],'statuses':[],'requests':[]}
    pending=bytearray();sequence=0
    try:
        with socket.create_connection((host,port),2) as connection:
            connection.settimeout(.05)
            result['local_endpoint']=list(connection.getsockname())
            def request(action):
                nonlocal sequence
                sequence+=1
                row=dict(v=1,source='eye',seq=sequence,device='all',action=action)
                result['requests'].append(row)
                start=time.monotonic();connection.sendall(json.dumps(row,separators=(',',':')).encode()+b'\n')
                while time.monotonic()-start<.35:
                    while b'\n' in pending:
                        wire,_,rest=pending.partition(b'\n');pending[:]=rest
                        frame=json.loads(wire)
                        if frame.get('type')=='telemetry':
                            result['telemetry']+=1
                            continue
                        if type(frame.get('seq')) is not int or frame['seq']!=sequence:continue
                        if frame.get('v')!=1 or frame.get('ok') is not True:raise ValueError('Rejected: '+str(frame.get('error')))
                        result['acks']+=1;result['rtt_ms'].append(round((time.monotonic()-start)*1000,3))
                        if isinstance(frame.get('status'),dict):result['statuses'].append(frame['status'])
                        return
                    try:chunk=connection.recv(16384)
                    except socket.timeout:continue
                    if not chunk:raise OSError('Peer disconnected')
                    pending.extend(chunk)
                    if len(pending)>65536:raise ValueError('Unbounded frame')
                raise TimeoutError('No matching ACK for '+action)
            request('hello');request('status')
            end=time.monotonic()+duration;count=0
            while time.monotonic()<end:
                tick=time.monotonic();request('heartbeat');count+=1
                if count%5==0:request('status')
                time.sleep(max(0,.1-(time.monotonic()-tick)))
            result['passed']=True
    except (OSError,ValueError,TypeError) as error:result['error']=str(error)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--host',required=True);parser.add_argument('--port',type=int,default=9000)
    args=parser.parse_args();result=probe(args.host,args.port)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    raise SystemExit(0 if result['passed'] else 1)
