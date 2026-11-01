"""Temporary real C3 station test; restore existing AP services in finally."""
import ipaddress
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

from commissioning_probe import probe


def command(*args):
    row=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=10)
    if row.returncode:raise RuntimeError('Command failed: '+args[0]+' '+args[1]+': '+row.stdout.decode('utf-8','replace')[-400:])
    return row.stdout.decode('utf-8','replace')


def run(config):
    if os.geteuid()!=0:raise PermissionError('Root required to manage the USB wireless interface')
    if config.get('ssid')!='NaoDun-Control' or not 8<=len(config.get('password',''))<=63:raise ValueError('Expected existing C3 WPA2 configuration')
    services=['guardianloop-ap.service','guardianloop-dhcp.service']
    active=[name for name in services if subprocess.run(['systemctl','is-active','--quiet',name]).returncode==0]
    result={'passed':False,'interface':'wlan0','transport':'Z15 USB Wi-Fi -> C3 AP -> S3 TCP 9000','services_before':active}
    signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(InterruptedError('Test terminated')))
    with tempfile.TemporaryDirectory(prefix='guardianloop-commissioning-',dir='/run') as directory:
        work=Path(directory);wpa=None;dhcp=None
        wpa_log=(work/'wpa.log').open('wb');dhcp_log=(work/'dhcp.log').open('wb')
        try:
            result['addresses_before']=json.loads(command('ip','-j','-4','addr','show','wlan0'))
            for service in reversed(active):command('systemctl','stop',service)
            command('ip','link','set','wlan0','down')
            command('iw','dev','wlan0','set','type','managed')
            command('ip','link','set','wlan0','up')
            try:
                scan=command('iw','dev','wlan0','scan','ssid','NaoDun-Control')
                result['scan_bss_count']=scan.count('BSS ')
                result['c3_scan_blocks']=[block[:1500] for block in scan.split('BSS ') if 'SSID: NaoDun-Control' in block][:2]
            except Exception as error:result['scan_error']=str(error)
            wpa_config=work/'station.conf'
            wpa_config.write_text('ctrl_interface='+str(work/'control')+'\nnetwork={\nssid='+json.dumps(config['ssid'])+'\npsk='+json.dumps(config['password'])+'\nscan_ssid=1\nkey_mgmt=WPA-PSK\n}\n')
            wpa_config.chmod(0o600)
            wpa=subprocess.Popen(['/sbin/wpa_supplicant','-i','wlan0','-D','nl80211','-c',str(wpa_config)],stdout=wpa_log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                link=command('iw','dev','wlan0','link')
                if 'Connected to ' in link:result['association']=link;break
                if wpa.poll() is not None:raise RuntimeError('Station supplicant exited')
                time.sleep(.5)
            if 'association' not in result:
                result['station_status']=command('wpa_cli','-p',str(work/'control'),'-i','wlan0','status')
                results=command('wpa_cli','-p',str(work/'control'),'-i','wlan0','scan_results')
                result['supplicant_c3_results']=[line for line in results.splitlines() if 'NaoDun-Control' in line]
                raise RuntimeError('C3 association timed out')
            capture=work/'capture.py'
            capture.write_text('import os,json\nfrom pathlib import Path\nif os.environ.get("reason") in ("BOUND","RENEW","REBIND","REBOOT"):\n Path('+repr(str(work/'lease.json'))+').write_text(json.dumps({k:os.environ.get(k) for k in ("reason","new_ip_address","new_subnet_mask","new_routers")}))\n')
            script=work/'dhcp-script';script.write_text('#!/bin/sh\n/usr/bin/python3 '+str(capture)+'\n');script.chmod(0o700)
            dhcp=subprocess.Popen(['/sbin/dhclient','-4','-1','-d','-sf',str(script),'-pf',str(work/'dhcp.pid'),'-lf',str(work/'leases'),'wlan0'],stdout=dhcp_log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+12
            while time.monotonic()<deadline and not (work/'lease.json').exists():time.sleep(.2)
            if not (work/'lease.json').exists():raise RuntimeError('C3 DHCP lease timed out')
            lease=json.loads((work/'lease.json').read_text());address=ipaddress.IPv4Address(lease['new_ip_address'])
            if address not in ipaddress.IPv4Network('192.168.4.0/24') or address==ipaddress.IPv4Address('192.168.4.2'):raise ValueError('Unexpected DHCP address')
            prefix=ipaddress.IPv4Network('0.0.0.0/'+lease['new_subnet_mask']).prefixlen
            command('ip','addr','add',str(address)+'/'+str(prefix),'dev','wlan0')
            result['lease']=lease;result['route_to_s3']=command('ip','-4','route','get','192.168.4.2')
            result['probe']=probe('192.168.4.2',9000,3);result['passed']=result['probe']['passed']
        except Exception as error:result['error']=str(error)
        finally:
            for process in (dhcp,wpa):
                if process and process.poll() is None:
                    process.terminate()
                    try:process.wait(3)
                    except subprocess.TimeoutExpired:process.kill();process.wait(2)
            wpa_log.close();dhcp_log.close()
            result['wpa_log_tail']=(work/'wpa.log').read_text(errors='replace').splitlines()[-15:]
            result['dhcp_log_tail']=(work/'dhcp.log').read_text(errors='replace').splitlines()[-10:]
            try:
                command('ip','addr','flush','dev','wlan0','scope','global')
                for service in active:command('systemctl','start',service)
                result['services_restored']={name:subprocess.run(['systemctl','is-active','--quiet',name]).returncode==0 for name in active}
                result['addresses_after']=json.loads(command('ip','-j','-4','addr','show','wlan0'))
                result['wireless_mode_after']=command('iw','dev','wlan0','info')
            except Exception as error:result['restore_error']=str(error)
    return result


if __name__=='__main__':
    result=run(json.loads(Path(sys.argv[1]).read_text()))
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    raise SystemExit(0 if result['passed'] and not result.get('restore_error') else 1)
