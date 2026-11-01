"""Prepare a reversible Z15 station profile; default is a read-only plan."""
import argparse,json,os,re,shutil,subprocess
from pathlib import Path
AP_SERVICES=('guardianloop-ap.service','guardianloop-dhcp.service')
UNMANAGED=Path('/etc/NetworkManager/conf.d/99-guardianloop-wlan0-unmanaged.conf')
PROFILE=Path('/etc/NetworkManager/system-connections/intent-one-c3.nmconnection')
def validate(config):
    if config.get('interface')!='wlan0' or config.get('z15_address')!='192.168.4.3/24' or config.get('gateway')!='192.168.4.1':raise ValueError('use documented interface/address plan')
    ssid,password=config.get('ssid'),config.get('password')
    if not isinstance(ssid,str) or not 1<=len(ssid.encode())<=32 or any(ch in ssid for ch in '\n\r;\\'):raise ValueError('invalid SSID')
    if not isinstance(password,str) or not 8<=len(password)<=63 or any(ch in password for ch in '\n\r;\\'):raise ValueError('private WPA2 password required')
    return config
def main():
    p=argparse.ArgumentParser();p.add_argument('config',type=Path);p.add_argument('--apply',action='store_true');p.add_argument('--rollback',action='store_true');a=p.parse_args()
    backup=Path('/var/lib/intent-one/network-backup')
    if not a.apply:
        print(json.dumps({'plan':'rollback' if a.rollback else 'C3 station','ssid':'NaoDun-Control','address':'192.168.4.3/24','writes':[str(PROFILE),str(UNMANAGED)],'ap_services_stopped':list(AP_SERVICES)}));return
    if os.geteuid()!=0:raise PermissionError('run on Z15 with sudo')
    def command(*args):subprocess.run(args,check=True,stdout=subprocess.DEVNULL)
    if a.rollback:
        record=json.loads((backup/'state.json').read_text())
        subprocess.run(['nmcli','connection','down','intent-one-c3'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if PROFILE.exists():PROFILE.unlink()
        if record['unmanaged_exists']:shutil.copy2(backup/'unmanaged.conf',UNMANAGED)
        elif UNMANAGED.exists():UNMANAGED.unlink()
        command('systemctl','restart','NetworkManager')
        for service in record['active_services']:command('systemctl','start',service)
        return
    config=validate(json.loads(a.config.read_text()))
    if (backup/'state.json').exists():raise RuntimeError('network backup already exists; rollback before reapplying')
    if PROFILE.exists():raise RuntimeError('station profile already exists')
    backup.mkdir(parents=True,mode=0o700)
    active=[s for s in AP_SERVICES if subprocess.run(['systemctl','is-active','--quiet',s]).returncode==0]
    (backup/'state.json').write_text(json.dumps(dict(unmanaged_exists=UNMANAGED.exists(),active_services=active)))
    if UNMANAGED.exists():shutil.copy2(UNMANAGED,backup/'unmanaged.conf')
    for service in active:command('systemctl','stop',service)
    UNMANAGED.write_text('[keyfile]\nunmanaged-devices=\n')
    text='[connection]\nid=intent-one-c3\ntype=wifi\ninterface-name=wlan0\nautoconnect=true\n[wifi]\nmode=infrastructure\nssid='+config['ssid']+'\n[wifi-security]\nkey-mgmt=wpa-psk\npsk='+config['password']+'\n[ipv4]\nmethod=manual\naddress1=192.168.4.3/24,192.168.4.1\n[ipv6]\nmethod=disabled\n'
    descriptor=os.open(PROFILE,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w') as profile:profile.write(text)
    command('systemctl','restart','NetworkManager');command('nmcli','connection','reload');command('nmcli','connection','up','intent-one-c3')
if __name__=='__main__':main()
