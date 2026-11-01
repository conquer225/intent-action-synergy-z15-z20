"""Read-only, bounded monitor evidence; never opens Cyton or writes brain state."""
import argparse
import json
from pathlib import Path
import subprocess
import time
from urllib.request import Request, build_opener, ProxyHandler


def summary(brain):
    fatigue=brain.get('fatigue',{});emotion=brain.get('emotion',{})
    return dict(state=brain.get('state'),seq=fatigue.get('seq'),
        fatigue_valid=fatigue.get('valid') is True,fatigue= fatigue.get('level'),
        emotion_valid=emotion.get('valid') is True,
        emotion=emotion.get('class_name',emotion.get('label')),
        calibration=fatigue.get('calibration_current'),
        packets=fatigue.get('packets_seen'))


def service_state():
    raw=subprocess.run(['systemctl','show','guardianloop-cyton','guardianloop-web',
        '-p','MainPID','-p','NRestarts','-p','ActiveState'],
        capture_output=True,text=True,check=True,timeout=3).stdout
    return raw.strip()


def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=60)
    args=p.parse_args()
    if not 5<=args.seconds<=90:raise ValueError('Bounded acceptance only')
    base=Path(__file__).resolve().parent
    opener=build_opener(ProxyHandler({}))
    key=(base/'access.key').read_text().strip()
    pid=subprocess.run(['systemctl','show','guardianloop-cyton','-p','MainPID','--value'],
        capture_output=True,text=True,check=True,timeout=3).stdout.strip()
    argv=Path('/proc/'+pid+'/cmdline').read_bytes().decode().split('\0')
    telemetry=Path(argv[argv.index('--telemetry-file')+1])
    report=dict(scope='live_readonly_monitor',rows=[],before=service_state(),
                physical_output_enabled=False,audio_output=False,raw_eeg_recorded=False)
    start=time.monotonic()
    while time.monotonic()-start<args.seconds:
        now=time.monotonic()
        try:
            request=Request('http://127.0.0.1:9117/api/player',headers={'X-Media-Key':key})
            with opener.open(request,timeout=3) as response:payload=json.load(response)
            player=payload.get('player',{});system=player.get('system') or {}
            mobile=summary(payload.get('brain',{}));hdmi=summary(system.get('brain',{}))
            live=json.loads(telemetry.read_text());runtime=live.get('runtime') or {}
            comparable=mobile['seq'] is not None and mobile['seq']==hdmi['seq']
            fields=('fatigue_valid','fatigue','emotion_valid','emotion','calibration','packets')
            row=dict(seconds=round(now-start,3),mobile=mobile,hdmi=hdmi,
                player_state=player.get('state'),session_id=player.get('session_id'),
                page=system.get('page'),frame=player.get('frame'),
                physical_output_enabled=system.get('physical_output_enabled'),
                mi_exit_enabled=system.get('mi_exit_enabled'),stimulus_enabled=system.get('stimulus_enabled'),
                comparable=comparable,parity=all(mobile[k]==hdmi[k] for k in fields) if comparable else None,
                telemetry_age_s=round(time.time()-live.get('updated_at',0),3),
                input_age_ms=runtime.get('input_age_at_snapshot_ms'),
                reader_queue_ms=runtime.get('reader_queue_delay_ms'),
                resets=runtime.get('primary_stream_resets'))
        except (OSError,ValueError,TimeoutError) as exc:
            row=dict(seconds=round(now-start,3),error=type(exc).__name__)
        report['rows'].append(row)
        print(json.dumps(row,ensure_ascii=False),flush=True)
        time.sleep(2)
    report['after']=service_state()
    report['services_unchanged']=report['before']==report['after']
    report['comparable_rows']=sum(row.get('comparable') is True for row in report['rows'])
    report['parity_failures']=sum(row.get('parity') is False for row in report['rows'])
    report['valid_prediction_rows']=sum(row.get('mobile',{}).get('emotion_valid') is True
        and row.get('mobile',{}).get('fatigue_valid') is True for row in report['rows'])
    report['timely_rows']=sum(row.get('input_age_ms') is not None and row['input_age_ms']<=3000
        for row in report['rows'])
    (base/'monitor-acceptance-20261007.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','before','after')},ensure_ascii=False))


if __name__=='__main__':main()
