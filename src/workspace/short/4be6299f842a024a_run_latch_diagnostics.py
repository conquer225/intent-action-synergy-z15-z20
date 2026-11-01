"""Read-only display/scheduler audit and separately requested phone STA join."""
import argparse
import ipaddress
import json
from pathlib import Path
import shlex
import sys
import time
import uuid

import run_live_system as board

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'phone_video_upload/output/latch_diagnostics_20261008'
sys.path.insert(0, str(ROOT / 'eeg_apps_z15'))
import connect_phone_hotspot as hotspot


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def command(client, args, root=False):
    return board.execute(client, shlex.join(args), root)


def network(client, media):
    before = board.audit(client, media)
    current = command(client, ['iw', 'dev', 'wlan0', 'link'])
    if 'SSID: QqqQ' in current:
        save('network.json', dict(already_connected=True, link=current,
                                 addresses=command(client, ['ip', '-br', 'addr'])))
        print('Z15_ALREADY_CONNECTED_TO_PHONE_HOTSPOT')
        return
    ap = command(client, ['iw', 'dev', 'wlan0', 'info'])
    if 'type AP' not in ap:
        raise ValueError('Unexpected wireless owner; do not replace its connection')
    for service in ('guardianloop-ap.service', 'guardianloop-dhcp.service'):
        if command(client, ['systemctl', 'is-active', service]).strip() != 'active':
            raise ValueError('Original AP service is not active')
    prefix = 'gl-phone-20261008-diag-' + uuid.uuid4().hex[:8]
    remote = '/home/xilinx/' + prefix
    with client.open_sftp() as ftp:
        with ftp.open(board.upload.trial.SAVED_NETWORK, 'r') as stream:
            station = stream.read().decode()
    if 'ssid="QqqQ"' not in station:
        raise ValueError('Saved connection does not match the user phone hotspot')
    station = '\n'.join('ctrl_interface=' + remote + '/control'
                        if line.startswith('ctrl_interface=') else line
                        for line in station.splitlines()) + '\n'
    command(client, ['mkdir', '-m', '700', remote])
    files = {'network.py': hotspot.BOARD_PROGRAM, 'dhcp_hook': hotspot.DHCP_HOOK,
             'station.conf': station,
             'dhclient.conf': 'timeout 25;\nretry 5;\nrequest subnet-mask, routers, domain-name-servers;\n',
             'state.json': json.dumps(dict(prefix=prefix, ap_active=True, dhcp_active=True))}
    with client.open_sftp() as ftp:
        for name, data in files.items():
            with ftp.open(remote + '/' + name, 'wx') as stream:
                stream.write(data)
            ftp.chmod(remote + '/' + name, 0o700 if name == 'dhcp_hook' else 0o600)
    # No credential or station configuration goes into the local evidence.
    station = files = None
    report = dict(remote=remote, prefix=prefix, before=before, ssid='QqqQ',
                  runtime_only=True, pc_wifi_changed=False, confirmed=False)
    save('network.json', report)
    timer = prefix + '-rollback.timer'
    command(client, ['systemd-run', '--unit=' + prefix + '-rollback', '--on-active=6min',
                     '--timer-property=AccuracySec=1s', '/usr/bin/python3',
                     remote + '/network.py', 'rollback'], True)
    try:
        command(client, ['/usr/bin/python3', remote + '/network.py', 'switch'], True)
        print('Z15_PHONE_HOTSPOT_JOIN_STARTED_WITH_WIRED_RECOVERY', flush=True)
        deadline = time.monotonic() + 55
        lease = None
        while time.monotonic() < deadline:
            with client.open_sftp() as ftp:
                try:
                    with ftp.open(remote + '/lease.json', 'r') as stream:
                        lease = json.loads(stream.read())
                except FileNotFoundError:
                    pass
            if lease:
                break
            time.sleep(2)
        if not lease:
            raise RuntimeError('No phone DHCP lease; AP recovery required')
        link = command(client, ['iw', 'dev', 'wlan0', 'link'])
        if 'SSID: QqqQ' not in link:
            raise ValueError('Lease is not from the requested phone hotspot')
        address = str(ipaddress.IPv4Interface(lease['address']).ip)
        http = command(client, ['curl', '--noproxy', '*', '-s', '-o', '/dev/null',
                                '-w', '%{http_code}', '--max-time', '5',
                                'http://' + address + ':9102/mobile'])
        after = board.audit(client, media)
        if after != before or http != '200':
            raise ValueError('Formal state or web admission changed during STA join')
        command(client, ['systemd-run', '--unit=' + prefix + '-guard',
                         '/usr/bin/python3', remote + '/network.py', 'guard'], True)
        command(client, ['systemctl', 'stop', timer], True)
        report.update(confirmed=True, board_ip=address, lease=lease, link=link, after=after,
                      web_http=http, addresses=command(client, ['ip', '-br', 'addr']))
        print('PHONE_MONITOR_URL http://' + address + ':9102/', flush=True)
    except Exception:
        command(client, ['/usr/bin/python3', remote + '/network.py', 'rollback'], True)
        report['original_ap_recovery_requested'] = True
        raise
    finally:
        save('network.json', report)


def audit(client, media):
    before = board.audit(client, media)
    library = media['eye_root'] + '/libtobii_display.so'
    sha = command(client, ['sha256sum', library]).split()[0]
    if sha != 'f0e12abe7901c3b98843a10135f1ce98d0507d3ef518a9836186ceab4d1e9da9':
        raise ValueError('Display library changed from the measured artifact')
    disassembly = {}
    for name in ('display_park', 'display_frames', 'display_index', 'display_status'):
        disassembly[name] = command(client, ['objdump', '--disassemble=' + name, library])
    paths = ('/proc/sys/kernel/sched_rt_runtime_us', '/proc/sys/kernel/sched_rt_period_us',
             '/proc/sys/kernel/sched_autogroup_enabled', '/proc/sys/kernel/timer_migration',
             '/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor',
             '/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq', '/proc/interrupts')
    installed = {}
    with client.open_sftp() as ftp:
        for path in paths:
            try:
                with ftp.open(path, 'r') as stream:installed[path] = stream.read().decode()
            except FileNotFoundError:installed[path] = None
    commands = {
        'kernel': ['uname', '-a'],
        'scheduler_threads': ['ps', '-eLo', 'pid,tid,psr,cls,rtprio,pri,ni,pcpu,comm', '--sort=-pcpu'],
        'cpu_load': ['cat', '/proc/loadavg'],
        'wireless': ['iw', 'dev', 'wlan0', 'link'],
        'cyton_usb': ['sh', '-c', 'if test -e /dev/ttyUSB0; then ls -l /dev/ttyUSB0; else printf "MISSING /dev/ttyUSB0\\n"; fi'],
        'usb_inventory': ['lsusb'],
        'usb_recent_kernel': ['journalctl', '-k', '--no-pager', '-n', '60'],
        'cyton_status': ['curl', '--noproxy', '*', '-s', '--max-time', '5',
                         'http://127.0.0.1:9102/api/status'],
        'ssvep_input': ['curl', '--noproxy', '*', '-s', '--max-time', '5',
                        'http://127.0.0.1:9102/api/ssvep-cue'],
        'trace_tools': ['sh', '-c', 'command -v perf; command -v trace-cmd; command -v cyclictest; true'],
    }
    results = {name:command(client, args, root=name=='usb_recent_kernel')
               for name,args in commands.items()}
    after = board.audit(client, media)
    report = dict(before=before, after=after, unchanged=after==before,
                  library_sha256=sha, disassembly=disassembly, installed=installed,
                  results=results, pl_loads=0, read_only=True)
    save('readonly-audit.json', report)
    if after != before:raise ValueError('Formal state changed during read-only inspection')
    live = json.loads(results['cyton_status'])
    input_state = json.loads(results['ssvep_input']).get('input', {})
    print(json.dumps(dict(formal_unchanged=True, library_sha256=sha,
                         input=input_state, status_keys=list(live),
                         trace_tools=results['trace_tools']), ensure_ascii=False))


def input_status(client, media):
    raw=command(client,['curl','--noproxy','*','-s','--max-time','5',
                        'http://127.0.0.1:9102/api/status'])
    status=json.loads(raw)
    fatigue=status.get('fatigue',{})
    selected={key:fatigue.get(key) for key in ('state','reason','packets_seen','seq',
        'calibration_current','calibration_total','dropped_packets','unresolved_gaps','signal_quality')}
    report=dict(server_time=status.get('server_time'),stale=status.get('stale'),
                eeg=selected,wireless=command(client,['iw','dev','wlan0','link']))
    save('input-'+str(time.time_ns())+'.json',report)
    print(json.dumps(report,ensure_ascii=False))


def scheduler(client, media):
    code='''import json, time, os
from pathlib import Path
ticks=os.sysconf('SC_CLK_TCK')
def snapshot():
    rows={}
    for task in Path('/proc').glob('[0-9]*/task/[0-9]*'):
        try:
            fields=(task/'stat').read_text().rsplit(')',1)[1].split()
            runtime=(int(fields[11])+int(fields[12]))*1000000000//ticks
            wait=slices=None
            if (task/'schedstat').exists():
                runtime,wait,slices=map(int,(task/'schedstat').read_text().split())
            rows[str(task)]=dict(pid=int(task.parts[2]),tid=int(task.name),
                name=(task/'comm').read_text().strip(),runtime=runtime,wait=wait,slices=slices)
        except (FileNotFoundError,ProcessLookupError):
            continue
    return rows
start=time.monotonic(); before=snapshot(); time.sleep(3); after=snapshot(); elapsed=time.monotonic()-start
rows=[]
for key,row in after.items():
    if key not in before: continue
    old=before[key]
    rows.append(dict(pid=row['pid'],tid=row['tid'],name=row['name'],
        cpu_percent=(row['runtime']-old['runtime'])/elapsed/1e7,
        runqueue_wait_ms=(row['wait']-old['wait'])/1e6 if row['wait'] is not None and old['wait'] is not None else None,
        slices=row['slices']-old['slices'] if row['slices'] is not None and old['slices'] is not None else None))
for row in rows:
    try:
        args=(Path('/proc')/str(row['pid'])/'cmdline').read_bytes().split(b'\\0')
        row['program']=Path(args[1].decode()).name if len(args)>1 and args[1] and b'python' in args[0] else Path(args[0].decode()).name
    except (FileNotFoundError,ProcessLookupError):
        row['program']=None
print(json.dumps(dict(elapsed=elapsed,clock_ticks=ticks,accounting='stat_ticks_with_schedstat_when_available',
    threads=sorted(rows,key=lambda r:r['cpu_percent'],reverse=True))))
'''
    sampled=json.loads(command(client,[board.PYTHON,'-c',code],True))
    settings={}
    paths=('/proc/sys/kernel/sched_min_granularity_ns','/proc/sys/kernel/sched_wakeup_granularity_ns',
           '/proc/sys/kernel/sched_latency_ns','/proc/sys/kernel/sched_schedstats')
    with client.open_sftp() as ftp:
        for path in paths:
            try:
                with ftp.open(path,'r') as handle:settings[path]=handle.read().decode().strip()
            except FileNotFoundError:settings[path]=None
    commands={
        'timer_resolution':['sh','-c',"grep -E 'hres_active|resolution|Clock Event' /proc/timer_list || true"],
        'kernel_config':['sh','-c',"if test -r /proc/config.gz; then zcat /proc/config.gz | grep -E 'CONFIG_(HIGH_RES_TIMERS|HZ_|NO_HZ|SCHEDSTATS|VIRT_CPU_ACCOUNTING|IRQ_TIME_ACCOUNTING|PREEMPT)'; else printf 'kernel config unavailable\\n'; fi"],
        'thread_classes':['ps','-eLo','pid,tid,psr,cls,rtprio,pri,ni,pcpu,comm','--sort=-pcpu'],
    }
    results={name:command(client,args,True) for name,args in commands.items()}
    save('scheduler-after.json',dict(sampled=sampled,settings=settings,results=results,
                                   read_only=True,no_priority_or_affinity_changes=True))
    print(json.dumps(dict(top_threads=sampled['threads'][:12],settings=settings,
                         timer_resolution=results['timer_resolution'],kernel_config=results['kernel_config']),ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('network', 'audit', 'input_status', 'scheduler'))
    args = parser.parse_args()
    media = json.loads(board.STATE.read_text())
    client = board.upload.trial.connect('192.168.2.99')
    try:globals()[args.action](client, media)
    finally:client.close()


if __name__ == '__main__':main()
