"""PC-only atlas build; ARM rendering uses NumPy and this checked artifact."""
import ast
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont


def main():
    root=Path(__file__).resolve().parent
    source=root/'z20_compute/headless_display.py'
    sources=[source,root/'z20_compute/headless_pipeline.py',root/'z20_compute/visual_display.py']
    strings=[node.value for path in sources for node in ast.walk(ast.parse(path.read_text(encoding='utf-8')))
             if isinstance(node,ast.Constant) and isinstance(node.value,str)]
    chars=''.join(sorted(set(''.join(strings)+''.join(chr(i) for i in range(32,127))+'？—–')))
    sizes=[20,28,40];cell=56
    masks=np.zeros((len(sizes),len(chars),cell,cell),np.uint8);widths=np.zeros((len(sizes),len(chars)),np.int16)
    font_path=Path('C:/Windows/Fonts/msyh.ttc')
    for slot,size in enumerate(sizes):
        font=ImageFont.truetype(str(font_path),size)
        for index,ch in enumerate(chars):
            image=Image.new('L',(cell,cell));ImageDraw.Draw(image).text((0,0),ch,font=font,fill=255,anchor='la')
            masks[slot,index]=np.array(image);widths[slot,index]=max(1,int(np.ceil(font.getlength(ch))))
    output=root/'artifacts/headless/display';output.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(output/'glyphs.npz',chars=np.array(chars),sizes=np.array(sizes),masks=masks,widths=widths)
    meta=dict(font=font_path.name,sizes=sizes,characters=len(chars),
              source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
              atlas_sha256=hashlib.sha256((output/'glyphs.npz').read_bytes()).hexdigest())
    (output/'glyphs.json').write_text(json.dumps(meta,indent=2),encoding='utf-8');print(meta)


if __name__=='__main__':main()
