"""Release integrity and a fixed, silent server command; no shell hooks."""
import hashlib
import ipaddress
import json
from pathlib import Path
import sys


def verify_release(root):
    root=Path(root).resolve();manifest=json.loads((root/'SHA256.json').read_text(encoding='utf-8'))
    if not isinstance(manifest,dict) or not 1<=len(manifest)<=5000:raise ValueError('invalid release manifest')
    for name,digest in manifest.items():
        path=root/name
        if (not isinstance(digest,str) or len(digest)!=64 or Path(name).is_absolute()
                or '..' in Path(name).parts or root not in path.resolve().parents or path.is_symlink()
                or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest):
            raise ValueError('release file differs: '+str(name))
    return dict(verified_files=len(manifest),manifest_sha256=hashlib.sha256((root/'SHA256.json').read_bytes()).hexdigest())


def server_command(root,config):
    root=Path(root).resolve()
    if (config.get('backend') not in ('pl','ps') or config.get('autostart') is not False
            or config.get('actuator_control') is not False
            or any(type(config.get(key)) is not bool for key in ('pipeline','hdmi','keys'))):
        raise ValueError('unsupported runtime configuration')
    ipaddress.ip_address(config['bind'])
    ports=[config.get('data_port'),config.get('http_port')]
    if any(type(p) is not int or not 1024<=p<=65535 or p==9000 for p in ports) or ports[0]==ports[1]:
        raise ValueError('distinct non-S3 data/HTTP ports required')
    command=[sys.executable,'-m','z20_compute.headless_server','--bind',config['bind'],'--port',str(ports[0]),
        '--http-port',str(ports[1]),'--backend',config['backend'],'--models',str(root/'models')]
    if config['pipeline']:
        command+=['--preview',str(root/'run/frame.png'),'--display-assets',str(root/'assets/display'),
            '--media-root',str(root/'media'),'--sound-root',str(root/'assets/sound')]
        for key in ('hdmi','keys'):
            if config[key]:command+=['--'+key]
        for key in ('calibration','record_pairs'):
            value=config.get(key)
            if value is not None:
                if not isinstance(value,str) or not value:raise ValueError('invalid '+key)
                command+=['--'+key.replace('_','-'),str((root/value).resolve())]
    elif config['hdmi'] or config['keys'] or config.get('calibration') or config.get('record_pairs'):
        raise ValueError('camera/display options require the pipeline')
    return command
