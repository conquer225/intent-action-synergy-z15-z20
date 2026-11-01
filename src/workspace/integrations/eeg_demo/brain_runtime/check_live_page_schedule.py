"""Finite production-lane scheduling check; no stimulus, USB command, PL or motor writes."""
import json
from pathlib import Path
import time

from cyton_trial_recorder import atomic_json

PAGE=Path('/dev/shm/gl-media-20261007-314e8796-system-page.json')
SSVEP=Path('/tmp/guardianloop-ssvep-shadow.json')
SEED=Path('/tmp/guardianloop-seed-shadow.json')


def main():
    if PAGE.exists():raise ValueError('Do not replace another page owner')
    observations=[]
    try:
        for page,reason in (('video','page_task_suspended'),('drive','page_task_resumed'),
                            ('video','page_task_suspended')):
            atomic_json(PAGE,dict(page=page,mode='live_readonly_hdmi',physical_output_enabled=False,
                updated_monotonic=time.monotonic(),reason='software_schedule_check_no_HDMI'))
            deadline=time.monotonic()+1.5
            while time.monotonic()<deadline:
                value=json.loads(SSVEP.read_text())
                if value.get('reason')==reason:break
                time.sleep(.05)
            assert value.get('reason')==reason,(page,value)
            assert value.get('valid') is False and value.get('control_enabled') is False
            observations.append(dict(page=page,ssvep_reason=value['reason'],valid=value['valid']))
        seed=json.loads(SEED.read_text())
        assert seed['valid'] is False and (seed.get('last_gap') or {}).get('reason')=='page_task_suspended'
    finally:
        if PAGE.exists():PAGE.unlink()
    print(json.dumps(dict(observations=observations,clean_exit_restores_standalone=True,
        seed_remains_paused=True,actual_HDMI_display_tested=False,physical_output_enabled=False)))


if __name__=='__main__':main()
