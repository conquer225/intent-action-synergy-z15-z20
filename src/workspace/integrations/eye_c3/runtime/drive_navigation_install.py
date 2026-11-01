"""Use the existing pinned display installer for this navigation-only update."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

BASE=Path('/home/xilinx/gl-hdmi-live-20261008-ea117349')
NAMES=('media_player.py','media_server.py','system_hdmi.py','system_mobile.js',
       'system_mobile.html','hdmi_stimulus.py','native_scan.py','libguardianloop_scan.so',
       'menu-shells-portrait-live.npz','media_state.json','boot-pins.json',
       'system_runtime/guardianloop_system/core.py')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('install','rollback'))
    args=parser.parse_args();stage=Path(__file__).resolve().parent
    if stage.parent!=Path('/home/xilinx') or not stage.name.startswith('gl-drive-navigation-20261014-'):
        raise ValueError('Use the private navigation-update stage')
    plan=json.loads((stage/'guard-plan.json').read_text())
    helper=stage/'display_restart_install.py'
    if hashlib.sha256(helper.read_bytes()).hexdigest()!=plan['installer_sha']:
        raise ValueError('Pinned display installer changed')
    dependency=stage/'install_calibration_repair.py'
    if hashlib.sha256(dependency.read_bytes()).hexdigest()!=plan['installer_dependency_sha']:
        raise ValueError('Pinned installer dependency changed')
    spec=importlib.util.spec_from_file_location('navigation_installer',helper)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.TARGETS={BASE/name for name in NAMES}
    getattr(module,args.action)(stage)


if __name__=='__main__':main()
