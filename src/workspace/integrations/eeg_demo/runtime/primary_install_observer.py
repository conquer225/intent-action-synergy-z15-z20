"""Read-only, finite record of HDMI identity across an acquisition update."""
import json
import argparse
from pathlib import Path
import subprocess
import time


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--post-install',action='store_true')
    args=parser.parse_args()
    stage=Path(__file__).resolve().parent
    plan=json.loads((stage/'deployment-plan.json').read_text())
    path=Path('/dev/shm')/(Path(plan['live']).name+'-player-status.json')
    units=['guardianloop-cyton.service',*plan['untouched_services']]
    deadline=time.monotonic()+60
    name='post-install-observation.jsonl' if args.post_install else 'restart-observation.jsonl'
    with (stage/name).open('x') as output:
        while time.monotonic()<deadline:
            fields=subprocess.check_output(['systemctl','show',*units,'-p','Id','-p','MainPID',
                                            '-p','ActiveState'],text=True,timeout=10)
            services={}
            for section in fields.strip().split('\n\n'):
                row=dict(line.split('=',1) for line in section.splitlines() if '=' in line)
                services[row.pop('Id')]=row
            player=json.loads(path.read_text()) if path.exists() else {}
            system=player.get('system') or {};brain=system.get('brain') or {}
            row=dict(monotonic=time.monotonic(),services=services,
                frame=player.get('frame'),player_state=player.get('state'),
                session_id=player.get('session_id'),status_age=time.monotonic()-player.get('updated_monotonic',0),
                acquisition_available=brain.get('acquisition_available'),brain_state=brain.get('state'),
                emotion_valid=(brain.get('emotion') or {}).get('valid'),
                fatigue_valid=(brain.get('fatigue') or {}).get('valid'),
                direction=system.get('direction'),physical_output=system.get('physical_output_enabled'),
                stimulus_enabled=system.get('stimulus_enabled'),
                runtime_directory_exists=Path('/run/guardianloop').is_dir())
            output.write(json.dumps(row)+'\n');output.flush()
            time.sleep(.5)


if __name__=='__main__':main()
