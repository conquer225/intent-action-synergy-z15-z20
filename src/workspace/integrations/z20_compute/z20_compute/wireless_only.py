"""Fail closed when production demo traffic would use a wired interface."""
import ipaddress,json,socket,struct,subprocess,sys
from pathlib import Path


def route_probe(host):
    if sys.platform=='win32':
        script="[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);$r=Find-NetRoute -RemoteIPAddress '"+host+"';$a=Get-NetAdapter -InterfaceIndex $r.InterfaceIndex;[pscustomobject]@{interface=$a.Name;wireless=($a.NdisPhysicalMedium -eq 9 -or $a.PhysicalMediaType -eq 'Native 802.11')}|ConvertTo-Json -Compress"
        result=subprocess.run(['powershell','-NoProfile','-Command',script],capture_output=True,text=True,encoding='utf-8',timeout=8)
        result.check_returncode();return json.loads(result.stdout)
    route=json.loads(subprocess.check_output(['ip','-j','route','get',host],timeout=5))[0]
    interface=route['dev'];node=Path('/sys/class/net')/interface
    return dict(interface=interface,wireless=(node/'wireless').exists() or (node/'phy80211').exists())


def require_wireless(host,*,probe=route_probe,allow_loopback=False):
    address=ipaddress.ip_address(host)
    if address.version!=4:raise ValueError('demo requires an explicit IPv4 address')
    if address.is_loopback:
        if allow_loopback:return dict(kind='loopback_test',interface='loopback',wireless=False)
        raise RuntimeError('loopback requires explicit offline simulation')
    try:result=probe(str(address))
    except (OSError,subprocess.SubprocessError,ValueError,KeyError,IndexError) as exc:
        raise RuntimeError('wireless route probe failed: '+str(exc)) from exc
    if result.get('wireless') is not True:raise RuntimeError('USB Wi-Fi required; wired route rejected')
    return dict(result,kind='wireless_route')


def require_wireless_bind(address):
    import fcntl
    address=str(ipaddress.IPv4Address(address))
    for node in Path('/sys/class/net').iterdir():
        if not ((node/'wireless').exists() or (node/'phy80211').exists()):continue
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            try:raw=fcntl.ioctl(sock.fileno(),0x8915,struct.pack('256s',node.name.encode()[:15]))
            except OSError:continue
            if socket.inet_ntoa(raw[20:24])==address:
                device=(node/'device').resolve()
                if not any(part.startswith('usb') for part in device.parts):
                    raise RuntimeError('wireless interface is not a USB device')
                return dict(interface=node.name,wireless=True,usb=True,device=str(device))
    raise RuntimeError('bind address is not assigned to a USB Wi-Fi interface')
