"""Fetch immutable, hash-recorded upstream visual sources for an offline demo."""
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import urllib.error

HERE=Path(__file__).resolve().parent


def get(url):
    for attempt in range(4):
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'Z20-visual-demo-source-audit'})
            with urllib.request.urlopen(request,timeout=40) as response:return response.read()
        except OSError:
            if attempt==3:raise
            time.sleep(1)


def main():
    root=HERE/'third_party/visual';root.mkdir(parents=True,exist_ok=True)
    records=[]
    for folder,repo,ref,names in (
        ('fluid','PavelDoGreat/WebGL-Fluid-Simulation','master',
         ('script.js','dat.gui.min.js','LDR_LLL1_0.png','LICENSE','README.md')),
        ('spectrum','conwayjw97/3D-Spectrogram','main',
         ('app.js','audio.js','ui.js','shaders.js','colours.js','index.html','LICENSE','README.md')),
        ('three','mrdoob/three.js','r155',
         ('build/three.module.js','examples/jsm/controls/OrbitControls.js','LICENSE'))):
        pin_path=root/(folder+'-pin.json')
        if pin_path.exists():commit=json.loads(pin_path.read_text())['commit']
        else:
            try:commit=json.loads(get('https://api.github.com/repos/'+repo+'/commits/'+ref))['sha']
            except urllib.error.HTTPError as exc:
                if exc.code!=403:raise
                commit=None
            pin_path.write_text(json.dumps(dict(repository=repo,commit=commit,ref=ref,
                pinning='commit' if commit else 'bundled file SHA256; GitHub API rate-limited'),indent=2),encoding='utf-8')
        for name in names:
            target=root/folder/name;target.parent.mkdir(parents=True,exist_ok=True)
            url='https://raw.githubusercontent.com/'+repo+'/'+(commit or ref)+'/'+name
            if not target.exists():target.write_bytes(get(url))
            records.append(dict(path=target.relative_to(root).as_posix(),url=url,
                sha256=hashlib.sha256(target.read_bytes()).hexdigest(),bytes=target.stat().st_size))
        print('VENDORED',repo,commit,flush=True)
    (root/'sources.json').write_text(json.dumps(dict(files=records),indent=2),encoding='utf-8')


if __name__=='__main__':main()
