"""Use the existing checksummed installer for the scoped phone/display update."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

BASE = Path('/home/xilinx/gl-hdmi-live-20261008-ea117349')
NAMES = ('media_server.py','media_player.py','system_hdmi.py','system_mobile.html',
         'system_mobile.js','hdmi_boot.py','menu-shells-portrait-live.npz','boot-pins.json')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('install','rollback','commit'))
    args=parser.parse_args();stage=Path(__file__).resolve().parent
    if stage.parent!=Path('/home/xilinx') or not stage.name.startswith('gl-shoot-ready-20261014-'):
        raise ValueError('Use the private board-local shooting stage')
    plan=json.loads((stage/'deployment-plan.json').read_text())
    for field in ('scoped_installer','installer_helper'):
        path=Path(plan[field])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=plan[field+'_sha']:
            raise ValueError('Existing installer helper changed')
    sys.path.insert(0,str(Path(plan['installer_helper']).parent))
    from install_calibration_repair import sha,replace,control,write_json
    spec=importlib.util.spec_from_file_location('scoped_install',plan['scoped_installer'])
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.__file__=str(stage/'install_shoot_ready.py')
    module.TARGETS={BASE/name for name in NAMES}
    module.sha=sha;module.replace=replace;module.control=control;module.write_json=write_json
    getattr(module,args.action)(stage,plan)
    print(json.dumps(json.loads((stage/'installation.json').read_text())),flush=True)


if __name__=='__main__':main()
