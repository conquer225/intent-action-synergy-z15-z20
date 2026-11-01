"""One bounded offline WLAN window; always reconnect the previous profile."""
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ps_tobii/tools'))
from serial_board import Board

OUT=Path(__file__).with_name('z15_tcp_relay.json')
record={'stage':'starting','temporary_relay':'192.168.2.1:19000 -> 192.168.4.2:9000','actuator_commands':False}


def wlan(*args):
    result=subprocess.run(['netsh','wlan',*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=8)
    return result.returncode,result.stdout.decode('gbk','replace')


def save():OUT.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')


try:
    _,before=wlan('show','interfaces')
    profile=re.search(r'^\s*Profile\s*:\s*(.+?)\s*$',before,re.M)
    if not profile:raise RuntimeError('Cannot identify current WLAN profile for restoration')
    original=profile.group(1);record['original_profile']=original;save()
    code,text=wlan('connect','name=NaoDun-Control','interface=WLAN');record['connect_request_exit']=code
    if code:raise RuntimeError('C3 WLAN connection request failed: '+text)
    connected=False;deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        try:
            with socket.create_connection(('192.168.4.2',9000),.5):connected=True;break
        except OSError:time.sleep(.5)
    if not connected:raise RuntimeError('C3 WLAN did not provide reachable S3 TCP within 12 seconds')
    record['s3_direct_tcp_reachable']=True;record['stage']='board_probe';save()
    board=Board('COM18')
    try:
        record['z15_route']=board.run('ip -4 route get 192.168.2.1',3)
        result=board.run('python3 /tmp/guardianloop_commissioning_probe.py --host 192.168.2.1 --port 19000',8)
        record['board_exit_code']=result['exit_code']
        record['probe']=json.loads(result['output'].strip())
    finally:board.close()
    record['stage']='probe_completed'
except Exception as error:record['error']=str(error);record['stage']='failed'
finally:
    if 'original' in globals():
        try:
            code,_=wlan('connect','name='+original,'interface=WLAN');record['restore_request_exit']=code
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                _,current=wlan('show','interfaces')
                match=re.search(r'^\s*Profile\s*:\s*(.+?)\s*$',current,re.M)
                if match and match.group(1)==original:record['wlan_restored']=True;break
                time.sleep(.5)
        except Exception as error:record['restore_error']=str(error)
    save()
