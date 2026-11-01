"""Real Z15-to-S3 wireless test using a temporary AP when C3 is unavailable."""
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time

from commissioning_probe import probe
from commissioning_wireless import command


def run(config):
    if os.geteuid()!=0:raise PermissionError('Root required for the temporary wireless AP')
    if config.get('ssid')!='NaoDun-Control' or not 8<=len(config.get('password',''))<=63:raise ValueError('Expected existing device WLAN configuration')
    active=[name for name in ('guardianloop-ap.service','guardianloop-dhcp.service') if subprocess.run(['systemctl','is-active','--quiet',name]).returncode==0]
    result={'passed':False,'transport':'temporary Z15 USB Wi-Fi AP -> real S3 station TCP 9000','c3_bypassed':True,'services_before':active}
    signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(InterruptedError('Test terminated')))
    with tempfile.TemporaryDirectory(prefix='guardianloop-ap-probe-',dir='/run') as directory:
        work=Path(directory);processes=[];streams=[]
        try:
            for service in reversed(active):command('systemctl','stop',service)
            original=Path('/etc/guardianloop/ap.conf').read_text()
            original=re.sub(r'^ctrl_interface=.*$', 'ctrl_interface='+str(work/'control'),original,flags=re.M)
            original=re.sub(r'^\s*ssid=.*$', '    ssid='+json.dumps(config['ssid']),original,flags=re.M)
            original=re.sub(r'^\s*psk=.*$', '    psk='+json.dumps(config['password']),original,flags=re.M)
            ap_config=work/'ap.conf';ap_config.write_text(original);ap_config.chmod(0o600)
            command('ip','link','set','wlan0','up');command('ip','addr','add','192.168.4.1/24','dev','wlan0')
            output=(work/'wpa.log').open('wb');streams.append(output)
            processes.append(subprocess.Popen(['/sbin/wpa_supplicant','-i','wlan0','-D','nl80211','-c',str(ap_config)],stdout=output,stderr=subprocess.STDOUT))
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                info=command('iw','dev','wlan0','info')
                if 'ssid NaoDun-Control' in info and 'type AP' in info:result['ap_info']=info;break
                time.sleep(.3)
            if 'ap_info' not in result:raise RuntimeError('Temporary AP startup timed out')
            leases=work/'leases'
            dns_config=work/'dnsmasq.conf';dns_config.write_text('interface=wlan0\nbind-interfaces\nport=0\ndhcp-authoritative\ndhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,10m\ndhcp-option=3,192.168.4.1\ndhcp-option=6,192.168.4.1\ndhcp-leasefile='+str(leases)+'\nlog-dhcp\n')
            output=(work/'dhcp.log').open('wb');streams.append(output)
            processes.append(subprocess.Popen(['/usr/sbin/dnsmasq','--keep-in-foreground','--conf-file='+str(dns_config),'--pid-file='+str(work/'dnsmasq.pid')],stdout=output,stderr=subprocess.STDOUT))
            deadline=time.monotonic()+18;host=None
            while time.monotonic()<deadline and host is None:
                if leases.exists():
                    for line in leases.read_text().splitlines():
                        fields=line.split()
                        if len(fields)<4:continue
                        address=ipaddress.IPv4Address(fields[2])
                        if address not in ipaddress.IPv4Network('192.168.4.0/24'):raise ValueError('Unexpected lease')
                        try:
                            with socket.create_connection((str(address),9000),.3):host=str(address);result['s3_lease']=fields[:4];break
                        except OSError:pass
                time.sleep(.3)
            if host is None:raise RuntimeError('No real S3 TCP endpoint arrived on the temporary AP')
            result['route_to_s3']=command('ip','-4','route','get',host)
            result['stations']=command('iw','dev','wlan0','station','dump')
            result['probe']=probe(host,9000,3);result['passed']=result['probe']['passed']
        except Exception as error:result['error']=str(error)
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(3)
                    except subprocess.TimeoutExpired:process.kill();process.wait(2)
            for stream in streams:stream.close()
            for name in ('wpa','dhcp'):
                path=work/(name+'.log')
                if path.exists():result[name+'_log_tail']=path.read_text(errors='replace').splitlines()[-12:]
            try:
                command('ip','addr','flush','dev','wlan0','scope','global')
                for service in active:command('systemctl','start',service)
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    info=command('iw','dev','wlan0','info')
                    if 'ssid GuardianLoop-Z15' in info and 'type AP' in info:break
                    time.sleep(.3)
                result['wireless_mode_after']=info
                result['services_restored']={name:subprocess.run(['systemctl','is-active','--quiet',name]).returncode==0 for name in active}
                result['addresses_after']=json.loads(command('ip','-j','-4','addr','show','wlan0'))
            except Exception as error:result['restore_error']=str(error)
    return result


if __name__=='__main__':
    result=run(json.loads(Path(sys.argv[1]).read_text()))
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    raise SystemExit(0 if result['passed'] and not result.get('restore_error') else 1)
