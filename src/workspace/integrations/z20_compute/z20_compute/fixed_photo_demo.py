"""Offline fixed-photo viewer; shares its rendered frames with future HDMI output."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .fixed_photo import FixedPhotoMemory, LABELS


DEFAULT_GALLERY = Path(__file__).resolve().parents[1] / 'artifacts' / 'fixed_photo_demo'
CHINESE_LABELS = ('人', '狗', '背景')


class PhotoDemo:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.files = json.loads((self.directory / 'gallery.json').read_text(encoding='utf-8'))['images']
        if not self.files:
            raise ValueError('gallery is empty')
        self.memory = FixedPhotoMemory.load(self.directory / 'model')
        self.index = 0

    def step(self, delta):
        self.index = (self.index + delta) % len(self.files)

    def current(self):
        with Image.open(self.directory / self.files[self.index]) as source:
            image = ImageOps.exif_transpose(source).convert('RGB')
        return image, self.memory.predict(np.asarray(image))


def _font(size, font_path=None):
    candidates = [font_path] if font_path else [
        'C:/Windows/Fonts/msyh.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return ImageFont.truetype(str(candidate), size)
    raise ValueError('Chinese font missing; pass --font with a CJK TrueType/OpenType font')


def render(demo, *, font_path=None):
    photo, result = demo.current()
    frame = Image.new('RGB', (1280, 720), '#fbf7ee')
    draw = ImageDraw.Draw(frame)
    ink, muted, accent = '#332c22', '#74644d', '#855f22'
    body, small, title = [_font(size, font_path) for size in (25, 20, 32)]
    draw.text((40, 24), 'Z20 · 固定图片三分类', font=title, fill=ink)
    draw.text((1050, 32), '{:02d} / {:02d}'.format(demo.index + 1, len(demo.files)), font=body, fill=muted)
    draw.line((40, 82, 1240, 82), fill='#d9ccb6', width=1)
    # Preserve the original aspect ratio and the whole photograph.
    fitted = ImageOps.contain(photo, (790, 500), Image.Resampling.LANCZOS)
    frame.paste(fitted, (40 + (790 - fitted.width) // 2, 105 + (500 - fitted.height) // 2))
    draw.text((875, 108), '识别结果', font=body, fill=muted)
    label = CHINESE_LABELS[result.class_id] if result.class_id is not None else '无法区分'
    draw.text((870, 155), label, font=_font(78, font_path), fill=ink)
    draw.text((875, 280), '模型分数', font=body, fill=muted)
    maximum = max(1, int(result.scores.max()))
    for index, score in enumerate(result.scores):
        y = 337 + index * 68
        draw.text((875, y), CHINESE_LABELS[index], font=body, fill=ink)
        draw.rectangle((959, y + 10, 1179, y + 23), fill='#e9e1d2')
        width = max(0, round(220 * int(score) / maximum))
        if width:
            draw.rectangle((959, y + 10, 959 + width, y + 23), fill=accent if index == result.class_id else '#b9ac91')
        draw.text((1194, y), str(int(score)), font=small, fill=ink)
    draw.text((875, 559), '已登记的 3 张照片', font=small, fill=muted)
    draw.text((875, 590), '电脑整数参考 · INT8', font=small, fill=muted)
    draw.line((40, 631, 1240, 631), fill='#d9ccb6', width=1)
    draw.text((40, 657), '← 上一张', font=body, fill=accent)
    draw.text((252, 657), '下一张 →', font=body, fill=accent)
    draw.text((712, 660), '空格切换    F11 全屏    Esc 退出', font=small, fill=muted)
    return frame


def export(demo, output, *, font_path=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for index, filename in enumerate(demo.files):
        demo.index = index
        _, result = demo.current()
        render(demo, font_path=font_path).save(output / ('preview_{}.png'.format(index)))
        records.append(dict(file=filename, class_id=result.class_id,
                            prediction=LABELS[result.class_id] if result.class_id is not None else None,
                            scores=result.scores.tolist(), backend=result.backend))
    report = dict(scope='same three registered photos; no held-out evaluation',
                  method='prototype weights in shared 1024-32-3 INT8 MLP',
                  board_executed=False, results=records)
    (output / 'results.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    demo.index = 0
    return report


def show(demo, *, font_path=None, smoke_output=None):
    import tkinter as tk
    from PIL import ImageTk
    root = tk.Tk()
    root.title('Z20 固定图片三分类 · 电脑预览')
    root.geometry('1280x720')
    root.resizable(False, False)
    label = tk.Label(root, borderwidth=0, highlightthickness=0, background='#fbf7ee')
    label.pack(fill='both', expand=True)

    def refresh(delta=0):
        demo.step(delta)
        label.photo = ImageTk.PhotoImage(render(demo, font_path=font_path))
        label.configure(image=label.photo)

    root.bind('<Right>', lambda event: refresh(1))
    root.bind('<space>', lambda event: refresh(1))
    root.bind('<Left>', lambda event: refresh(-1))
    root.bind('<Escape>', lambda event: root.destroy())
    root.bind('<F11>', lambda event: root.attributes('-fullscreen', not root.attributes('-fullscreen')))
    label.bind('<Button-1>', lambda event: refresh(-1 if event.x < 230 else 1) if event.y >= 631 else None)
    refresh()
    if smoke_output:
        def check_keys():
            root.focus_force()
            root.update()
            root.event_generate('<Right>')
            root.update()
            right = demo.index
            root.event_generate('<Left>')
            root.update()
            left = demo.index
            root.event_generate('<space>')
            root.update()
            space = demo.index
            Path(smoke_output).write_text(json.dumps(dict(right=right, left=left, space=space,
                passed=(right, left, space) == (1, 0, 1))), encoding='utf-8')
            root.destroy()
            if (right, left, space) != (1, 0, 1):
                raise RuntimeError('desktop key bindings failed')
        root.after(150, check_keys)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gallery', type=Path, default=DEFAULT_GALLERY)
    parser.add_argument('--export', type=Path)
    parser.add_argument('--font')
    parser.add_argument('--smoke-output', type=Path)
    args = parser.parse_args()
    demo = PhotoDemo(args.gallery)
    if args.export:
        print(json.dumps(export(demo, args.export, font_path=args.font), ensure_ascii=False, indent=2))
    else:
        show(demo, font_path=args.font, smoke_output=args.smoke_output)


if __name__ == '__main__':
    main()
