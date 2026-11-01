"""Explicit local source choice for an already-running KEY1 demonstration."""
import argparse,json,os,uuid
from pathlib import Path
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--media-root',type=Path,required=True);p.add_argument('mode',choices=('replay',));a=p.parse_args()
 folder=a.media_root.resolve()/'vision_demo'
 if not (folder/'replay/replay.json').is_file():raise SystemExit('Signal extension is not installed')
 target=folder/'source_selection.json';temporary=target.with_suffix('.tmp')
 temporary.write_text(json.dumps(dict(mode=a.mode,request_id=uuid.uuid4().hex))+'\n',encoding='utf-8');os.replace(str(temporary),str(target))
 print('Source choice requested:',a.mode,'(no capture/calibration/actuator writes)')
