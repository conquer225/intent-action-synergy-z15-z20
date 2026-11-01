"""Use canonical audio asset paths for the existing no-symlinks boot verifier."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
LIVE = Path('/home/xilinx/gl-hdmi-live-20261008-ea117349')


def main():
    target = LIVE/'boot-pins.json'
    plan = json.loads((ROOT/'plan.json').read_text())
    row = next(row for row in plan['files'] if row['target'] == str(target))
    before = target.read_bytes()
    if hashlib.sha256(before).hexdigest() != row['new_sha']:
        raise RuntimeError('Installed pins changed after transaction')
    pins = json.loads(before)
    changed = {}
    for name, expected in list(pins['files'].items()):
        path = Path(name)
        if not path.is_symlink():
            continue
        if not name.startswith('/home/xilinx/gl-audio-level-20261016-DMoJIj/'):
            raise RuntimeError('Unexpected existing non-audio symlink pin')
        actual = path.resolve(strict=True)
        if hashlib.sha256(actual.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Canonical audio asset differs')
        del pins['files'][name]
        pins['files'][str(actual)] = expected
        changed[name] = str(actual)
    if not changed:
        raise RuntimeError('Expected audio symlink pin not present')
    shutil.copy2(target, ROOT/'boot-pins-before-canonical.json')
    pending = target.with_suffix('.canonical-new')
    pending.write_text(json.dumps(pins, indent=2))
    pending.chmod(0o600)
    pending.replace(target)
    shutil.copy2(target, ROOT/'payload'/row['key'])
    row['new_sha'] = hashlib.sha256(target.read_bytes()).hexdigest()
    (ROOT/'plan.json').write_text(json.dumps(plan, indent=2))
    # The real boot validator is read-only; do not invoke main()/activate().
    import sys
    sys.path.insert(0, str(LIVE))
    from hdmi_boot import verified_state
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    verified_state(LIVE, boot, plan['acquisition_pid'], pins['files'])
    result = dict(changed=changed, real_boot_validator_passed=True,
                  restarted=False, boot_image_modified=False)
    (ROOT/'canonical-pins.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
