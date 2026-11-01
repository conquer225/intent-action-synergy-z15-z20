"""Prepare static panels on the PC using copies of the board's exact fonts."""
import hashlib
import json
from pathlib import Path
import sys
import time

import run_live_system as helpers
from system_hdmi import UnifiedDisplay

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'phone_video_upload/output/load_relief_20261007/menu_assets'


def main():
    OUT.mkdir(parents=True,exist_ok=True);eye=OUT/'eye';(eye/'src').mkdir(parents=True,exist_ok=True)
    c=helpers.upload.trial.connect('192.168.2.99')
    state=json.loads(helpers.STATE.read_text())
    try:
        with c.open_sftp() as ftp:
            for name in ('guide_render.py','guide.py','validation.py','selection.py'):
                ftp.get(state['eye_root']+'/src/'+name,str(eye/'src'/name))
            for remote,name in (
                ('/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf','cjk.ttf'),
                ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','latin.ttf'),
            ):ftp.get(remote,str(OUT/name))
    finally:c.close()
    sys.path.insert(0,str(ROOT))
    started=time.perf_counter()
    display=UnifiedDisplay(eye,live=True,dimensions=(288,512),font_paths=(OUT/'cjk.ttf',OUT/'latin.ttf'))
    cache=OUT/'menu-shells-portrait-live.npz';display.save_shell_cache(cache)
    cached=UnifiedDisplay(eye,live=True,dimensions=(288,512),font_paths=(OUT/'cjk.ttf',OUT/'latin.ttf'),shell_cache=cache)
    if any(not (display.shells[page]==cached.shells[page]).all() for page in display.shells):
        raise ValueError('Prepared panel pixels changed')
    report=dict(pages=len(display.shells),sha256=hashlib.sha256(cache.read_bytes()).hexdigest(),
                bytes=cache.stat().st_size,pc_prepare_seconds=time.perf_counter()-started,
                exact_cache_roundtrip=True,contract=display.shell_contract)
    (OUT/'preparation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({key:report[key] for key in ('pages','bytes','pc_prepare_seconds','exact_cache_roundtrip')}))


if __name__=='__main__':main()
