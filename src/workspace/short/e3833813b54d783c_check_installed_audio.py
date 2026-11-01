"""Exercise actual unified UI audio commands, leaving the static home afterwards."""
import json
from pathlib import Path
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
LIVE = Path('/home/xilinx/gl-hdmi-live-20261008-ea117349')
URL = 'http://127.0.0.1:9119/api/player'
KEY = (LIVE/'access.key').read_text().strip()


def api(data=None):
    request = urllib.request.Request(URL, data=json.dumps(data).encode() if data else None,
        headers={'X-Media-Key':KEY, 'Origin':'http://127.0.0.1:9119',
                 'Content-Type':'application/json'})
    with urllib.request.urlopen(request, timeout=4) as response:
        return json.load(response)


def command(action, value=None, **fields):
    result = api(dict(action=action, value=value, **fields))
    deadline = time.monotonic()+5
    while True:
        row = api()['player']
        receipt = row.get('command_receipt') or {}
        if receipt.get('id') == result['command_id']:
            if receipt['state'] != 'applied':
                raise RuntimeError('Command rejected: '+str(receipt))
            break
        if time.monotonic() > deadline:
            raise RuntimeError('Command receipt timed out: '+action)
        time.sleep(.15)
    deadline = time.monotonic()+4
    while (row.get('system') or {}).get('reading'):
        if time.monotonic() > deadline:
            raise RuntimeError('Menu did not finish reading period')
        time.sleep(.15)
        row = api()['player']
    return row


def observe(name, seconds):
    rows = []
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        row = api()['player']
        rows.append({k:row.get(k) for k in ('state','page','audio','frame','error','runtime_guard')})
        time.sleep(.2)
    return dict(name=name, samples=rows,
                feeding_seen=any((r.get('audio') or {}).get('player', {}).get('phase') == 'feeding' for r in rows),
                errors=[r['audio']['player'] for r in rows
                        if (r.get('audio') or {}).get('player', {}).get('phase') == 'error'])


def main():
    report = dict(audibility_requires_user_confirmation=True, motors_commanded=False, phases=[])
    try:
        command('home')
        command('choose', 1)
        command('choose', 0)
        report['phases'].append(observe('water', 3))
        command('choose', 2)
        report['phases'].append(observe('help', 3))
        command('home')
        command('choose', 2)
        command('choose', 2)
        report['phases'].append(observe('music', 5))
        command('volume', 30)
        report['phases'].append(observe('volume30', 1.5))
        command('volume', 40)
        command('home')
        report['after_music_exit'] = observe('home_audio_stopped', 1)
        command('video', id='d87609d9be1c4738ba9dc378438d9935')
        report['phases'].append(observe('uploaded_video', 6))
    except Exception as error:
        report['error'] = str(error)
    finally:
        command('home')
        report['final'] = observe('home', 2)
        report['finished'] = True
        (ROOT/'ui-acceptance.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
