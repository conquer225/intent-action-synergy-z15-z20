"""Desktop preview and pre-rendered HDMI frames for three reviewed scenes."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .fixed_scene import FixedSceneMemory, describe_scene


DEFAULT_GALLERY = Path(__file__).resolve().parents[1] / 'artifacts' / 'person_dog'
INTERACTION_ZH = {'holding': '人抱着狗', 'petting': '人摸狗', 'leashing': '人牵着狗',
                  'walking_with_dog': '人遛狗'}
POSITION_ZH = {'person_left_of_dog': '人在狗的左边',
               'person_right_of_dog': '人在狗的右边',
               'same_horizontal_position': '人和狗横向居中相同'}


def _font(size):
    for path in ('C:/Windows/Fonts/msyh.ttc',
                 '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
                 '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise ValueError('CJK font required for rendering')


class SceneDemo:
    def __init__(self, directory, backend=None):
        self.directory = Path(directory)
        gallery = json.loads((self.directory / 'gallery.json').read_text(encoding='utf-8'))
        if gallery.get('format') != 'z20-person-dog-gallery-v1' or len(gallery['images']) != 3:
            raise ValueError('expected reviewed three-scene gallery')
        self.files = gallery['images']
        self.memory = FixedSceneMemory.load(self.directory / 'model')
        self.backend = backend
        self.index = 0

    def step(self, delta):
        self.index = (self.index + delta) % len(self.files)

    def current(self):
        entry = self.files[self.index]
        with Image.open(self.directory / entry['file']) as source:
            image = source.convert('RGB')
        prediction = self.memory.recognize(np.asarray(image), backend=self.backend)
        scene = None if prediction.scene_id is None else describe_scene(
            self.files[prediction.scene_id], image.size)
        return image, prediction, scene


def render(demo, *, board_controls=False):
    photo, prediction, scene = demo.current()
    frame = Image.new('RGB', (1280, 720), '#faf8f3')
    draw = ImageDraw.Draw(frame)
    ink, muted = '#262421', '#655f57'
    draw.text((42, 22), 'Z20 · 人狗固定场景', font=_font(31), fill=ink)
    draw.text((1058, 31), '{:02d} / 03'.format(demo.index + 1), font=_font(22), fill=muted)
    draw.line((40, 82, 1240, 82), fill='#d5cec2', width=2)
    photo = photo.resize((720, 540), Image.Resampling.LANCZOS)
    frame.paste(photo, (40, 100))
    if scene is not None:
        for label, color, chinese in [('person', '#d3332c', '人'), ('dog', '#29974d', '狗')]:
            x0, y0, x1, y1 = scene['boxes'][label]
            scaled = (40 + round(x0 * 1.125), 100 + round(y0 * 1.125),
                      40 + round(x1 * 1.125), 100 + round(y1 * 1.125))
            draw.rectangle(scaled, outline=color, width=4)
            draw.text((scaled[0] + 4, max(100, scaled[1] - 29)), chinese,
                      font=_font(22), fill=color, stroke_width=2, stroke_fill='white')
        if scene['geometry'] is not None:
            centers = [(40 + (box[0] + box[2]) * .5625,
                        100 + (box[1] + box[3]) * .5625)
                       for box in (scene['boxes']['person'], scene['boxes']['dog'])]
            draw.line(centers, fill='white', width=8)
            draw.line(centers, fill=ink, width=3)
            for center, color in zip(centers, ('#d3332c', '#29974d')):
                x, y = center
                draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=color,
                             outline='white', width=2)
            text = '{:.2f} m（中心间距）'.format(scene['geometry']['distance_m'])
            font = _font(20)
            bounds = draw.textbbox((0, 0), text, font=font)
            width = bounds[2] - bounds[0]
            x = min(748 - width, max(52, sum(p[0] for p in centers) / 2 - width / 2))
            y = min(597, max(110, max(p[1] for p in centers) + 14))
            draw.rectangle((x - 6, y - 3, x + width + 6, y + 29), fill='#faf8f3')
            draw.text((x, y), text, font=font, fill=ink)
    draw.text((810, 107), '识别出的固定场景', font=_font(22), fill=muted)
    if scene is None:
        draw.text((810, 165), '未识别', font=_font(45), fill=ink)
    else:
        draw.text((810, 165), INTERACTION_ZH[scene['interaction']], font=_font(45), fill=ink)
        draw.text((810, 258), POSITION_ZH[scene['position']], font=_font(27), fill=ink)
    geometry = None if scene is None else scene['geometry']
    draw.text((810, 322), '人狗中心间距（估算）', font=_font(22), fill=muted)
    draw.text((810, 364), '--' if geometry is None else
              '{:.2f} m'.format(geometry['distance_m']), font=_font(46), fill=ink)
    if geometry is not None:
        draw.text((810, 450), '人深度 Z   {:.2f} m'.format(geometry['person_depth_m']),
                  font=_font(24), fill=ink)
        draw.text((810, 492), '狗深度 Z   {:.2f} m'.format(geometry['dog_depth_m']),
                  font=_font(24), fill=ink)
        draw.text((810, 538), '单张照片 · 参考尺度计算', font=_font(18), fill=muted)
    draw.text((810, 580), '模型整数分数（抱 / 摸 / 牵）', font=_font(18), fill=muted)
    draw.text((810, 610), ' / '.join(str(int(s)) for s in prediction.scores),
              font=_font(22), fill=ink)
    draw.line((40, 655, 1240, 655), fill='#d5cec2', width=2)
    controls = ('串口输入 n 下一张    p 上一张    q 退出' if board_controls else
                '← 上一张     下一张 →     空格切换     Esc 退出')
    draw.text((42, 667), controls,
              font=_font(19), fill=muted)
    return frame


def export(demo, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for index in range(len(demo.files)):
        demo.index = index
        photo, prediction, scene = demo.current()
        render(demo).save(output / ('preview_{}.png'.format(index)))
        if scene is not None and scene['geometry'] is not None:
            reference_image = photo.copy()
            drawing = ImageDraw.Draw(reference_image)
            drawing.text((12, 12), '尺度参考登记', font=_font(20), fill='black',
                         stroke_width=2, stroke_fill='white')
            for label, chinese, color in (('person', '人', '#d3332c'), ('dog', '狗', '#29974d')):
                item = scene['geometry']['reference_inputs'][label]
                a, b = [tuple(point) for point in item['segment_px']]
                drawing.line((a, b), fill=color, width=4)
                for x, y in (a, b):
                    drawing.line((x - 5, y, x + 5, y), fill=color, width=3)
                text = '{}参考 {:.2f} m'.format(chinese, item['length_m'])
                x = min(470, a[0] + 10)
                drawing.text((x, a[1]), text, font=_font(18), fill=color,
                             stroke_width=2, stroke_fill='white')
            reference_image.save(output / ('reference_{}.png'.format(index)))
        records.append(dict(input=demo.files[index]['file'], scene_id=prediction.scene_id,
                            scores=prediction.scores.tolist(), backend=prediction.backend,
                            position=None if scene is None else scene['position'],
                            interaction=None if scene is None else scene['interaction'],
                            boxes=None if scene is None else scene['boxes'],
                            geometry=None if scene is None else scene['geometry']))
    demo.index = 0
    report = dict(scope='three registered demonstration images only',
                  annotations='manual review, selected by inferred scene ID',
                  board_executed=False, results=records)
    (output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                         encoding='utf-8')
    return report


def show(demo):
    import tkinter as tk
    from PIL import ImageTk
    root = tk.Tk()
    root.title('Z20 人狗固定场景 · 电脑预览')
    root.geometry('1280x720')
    label = tk.Label(root, borderwidth=0, highlightthickness=0)
    label.pack(fill='both', expand=True)
    def refresh(delta=0):
        demo.step(delta)
        label.photo = ImageTk.PhotoImage(render(demo))
        label.configure(image=label.photo)
    root.bind('<Left>', lambda event: refresh(-1))
    root.bind('<Right>', lambda event: refresh(1))
    root.bind('<space>', lambda event: refresh(1))
    root.bind('<Escape>', lambda event: root.destroy())
    refresh()
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gallery', type=Path, default=DEFAULT_GALLERY)
    parser.add_argument('--export', type=Path)
    args = parser.parse_args()
    demo = SceneDemo(args.gallery)
    if args.export:
        print(json.dumps(export(demo, args.export), ensure_ascii=False, indent=2))
    else:
        show(demo)


if __name__ == '__main__':
    main()
