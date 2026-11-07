"""Explicit local launcher. Never changes Wi-Fi, loads PL, or installs startup."""
import argparse,json,os,secrets,sys
from pathlib import Path
from z20_compute.release import verify_release
from z20_compute.wireless_only import require_wireless,require_wireless_bind

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('init-config','verify','doctor','board','pc'))
    parser.add_argument('--config',type=Path,default=ROOT/'private/demo.json')
    parser.add_argument('--host');parser.add_argument('--seconds',type=float,default=0)
    parser.add_argument('--pl-map',action='store_true',help='board: enable the selectable PL map renderer')
    parser.add_argument('--map-manifest',type=Path,help='pc: reuse an existing known-pose fusion manifest')
    args=parser.parse_args()
    if args.action=='init-config':
        import ipaddress
        if not args.host:parser.error('--host is the Z20 USB Wi-Fi IPv4')
        ip=ipaddress.IPv4Address(args.host)
        if not ip.is_private or ip.is_unspecified or ip.is_loopback:parser.error('private WLAN IPv4 required')
        args.config.parent.mkdir(parents=True,exist_ok=True)
        if args.config.exists() or (args.config.parent/'token.txt').exists():raise ValueError('private config already exists')
        token=secrets.token_hex(24)
        for path,text in ((args.config,json.dumps(dict(host=str(ip),token_file='token.txt'),indent=2)),(args.config.parent/'token.txt',token+'\n')):
            with path.open('x',encoding='utf-8') as stream:stream.write(text)
            path.chmod(0o600)
        print('PRIVATE_CONFIG_CREATED '+str(args.config));return
    if args.action=='verify':print(json.dumps(verify_release(ROOT),indent=2));return
    row=json.loads(args.config.read_text(encoding='utf-8'));token=(args.config.parent/row['token_file']).resolve()
    if args.action=='doctor':
        report=dict(silent=True,firmware_loaded_by_tool=False,wireless_verified=False,checks={})
        for name,fn in (
            ('release',lambda:verify_release(ROOT)),
            ('wireless',lambda:require_wireless_bind(row['host']) if sys.platform.startswith('linux') else require_wireless(row['host'])),
            ('token',lambda:dict(present=token.is_file(),length_valid=32<=len(token.read_text().strip())<=128))):
            try:report['checks'][name]=dict(ok=True,result=fn())
            except Exception as exc:report['checks'][name]=dict(ok=False,error=str(exc))
        report['uio']={p.name:(p/'name').read_text().strip() for p in Path('/sys/class/uio').glob('uio*')}
        report['wifi_acceptance_pending']=['association','client_isolation','10_fps','500ms_ack_p95','10min_combined_soak']
        print(json.dumps(report,indent=2));return
    verify_release(ROOT)
    if args.action=='board':
        if not sys.platform.startswith('linux'):raise RuntimeError('board entry requires Navigator Linux')
        require_wireless_bind(row['host'])
        names={(p/'name').read_text().strip() for p in Path('/sys/class/uio').glob('uio*')}
        missing={'navigator-mlp','navigator-npu-dma','z20-video-observer'}-names
        if missing:raise RuntimeError('matching Navigator PL/DT not running: '+str(sorted(missing)))
        command=[sys.executable,'-m','z20_compute.headless_server','--bind',row['host'],'--backend','pl',
            '--models',str(ROOT/'models'),'--preview',str(ROOT/'run/frame.png'),
            '--display-assets',str(ROOT/'assets/display'),'--sound-root',str(ROOT/'assets/sound'),
            '--media-root',str(ROOT/'media'),'--hdmi','--visual-token-file',str(token),
            '--visual-codec',str(ROOT/'assets/display/libz20_visual.so')]
        if args.pl_map:command+=['--pl-map']
        (ROOT/'media').mkdir(exist_ok=True);(ROOT/'run').mkdir(exist_ok=True)
    else:
        require_wireless(row['host'])
        command=[sys.executable,'-m','z20_compute.visual_host','--host',row['host'],'--token-file',str(token),
            '--model',str(ROOT/'build/reconstruction/models/yolo26m-depth.pt')]
        if args.seconds:command+=['--seconds',str(args.seconds)]
        if args.map_manifest:command+=['--map-manifest',str(args.map_manifest.resolve())]
    os.chdir(ROOT);os.execv(sys.executable,command)


if __name__=='__main__':main()
