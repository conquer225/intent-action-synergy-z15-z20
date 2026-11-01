"""Render recorded-scene stereo versus YOLO26 qualitative reconstruction evidence."""
import argparse
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

from z20_compute.depth_surface import depth_surface


def render(root):
    root = Path(root)
    font = Path('C:/Windows/Fonts/msyh.ttc')
    if font.exists():
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams['axes.unicode_minus'] = False
    stereo = np.load(root/'stereo/depth-0000000000.npz', allow_pickle=False)
    records = [json.loads((root/name/'result.json').read_text(encoding='utf-8'))
               for name in ('yolo26n-left', 'yolo26m-left')]
    stereo_record = json.loads((root/'stereo/latest.json').read_text(encoding='utf-8'))
    source = cv2.imread(str(root/'yolo26n-left/input.png'))
    fig = plt.figure(figsize=(17, 8.7), constrained_layout=True)
    titles = ['同一张真实录制图', '旧双目：有较多缺口', 'YOLO26n：预测深度', 'YOLO26m：预测深度']
    axes = [fig.add_subplot(2, 4, i+1) for i in range(4)]
    axes[0].imshow(cv2.cvtColor(source, cv2.COLOR_BGR2RGB))
    valid = stereo['valid_mask']
    depth = stereo['xyz'][:, :, 2].copy()
    depth[~valid] = np.nan
    depth /= np.nanmedian(depth)
    depths = [depth] + [np.load(root/name/'depth-relative.npy')
                        for name in ('yolo26n-left', 'yolo26m-left')]
    finite = np.concatenate([v[np.isfinite(v)] for v in depths])
    low, high = np.percentile(finite, [2, 98])
    for ax, values in zip(axes[1:], depths):
        picture = ax.imshow(values, cmap='turbo', vmin=low, vmax=high)
    for ax, title in zip(axes, titles):
        ax.set_title(title, fontsize=11)
        ax.axis('off')
    fig.colorbar(picture, ax=axes[1:], shrink=.7, label='各方法深度 / 各自中位深度')
    notes = fig.add_subplot(2, 4, 5)
    notes.axis('off')
    notes.text(0, .95,
        '本图比较表面连续性，不是精度评测。\n\n'
        f'旧双目：{int(valid.sum()):,} 个有效点\n'
        f'平面模型内点占比 {stereo_record["homography_inlier_ratio"]:.1%}\n'
        f'校正后垂直残差 P95 {stereo_record["rectified_vertical_p95_px"]:.2f} px\n\n'
        '神经网络输出是单目推断，\n'
        '细线、印刷纹理仍可能出错。\n\n'
        '这里只重建可见表面；\n'
        '背面、多视角拼接和实测尺度\n'
        '尚未验证。', va='top', fontsize=11, linespacing=1.55)
    for index in range(3):
        ax = fig.add_subplot(2, 4, index+6, projection='3d')
        if index == 0:
            points = stereo['xyz'][valid]
            points = points / np.median(points[:, 2])
            colors = cv2.cvtColor(stereo['rectified0'], cv2.COLOR_BGR2RGB)[valid]/255.
            ax.scatter(points[::5, 0], points[::5, 2], -points[::5, 1],
                       c=colors[::5], s=.45, depthshade=False)
            title = '旧双目散点'
        else:
            name = ('yolo26n-left', 'yolo26m-left')[index-1]
            record = records[index-1]
            relative = np.load(root/name/'depth-relative.npy')
            surface = depth_surface(relative, source,
                                    np.asarray(record['assumed_intrinsics']), stride=6)
            vertices = surface.vertices[:, [0, 2, 1]].copy()
            vertices[:, 2] *= -1
            colors = surface.colors[surface.faces].mean(axis=1)/255.
            collection = Poly3DCollection(vertices[surface.faces], facecolors=colors,
                                          linewidths=0, edgecolors='none')
            ax.add_collection3d(collection)
            title = ('YOLO26n 可见表面', 'YOLO26m 可见表面')[index-1]
        ax.set_xlim(-.65, .65); ax.set_ylim(.65, 1.35); ax.set_zlim(-.5, .5)
        ax.set_box_aspect((1.3, .7, 1.))
        ax.view_init(elev=18, azim=-68)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel('横向'); ax.set_ylabel('相对深度'); ax.set_zlabel('高度')
        ax.tick_params(labelsize=7)
    fig.suptitle('保存的实拍帧：双目几何诊断与单目深度预览（均未做实物精度验证）', fontsize=14)
    fig.savefig(root/'comparison.png', dpi=145)
    plt.close(fig)
    print(root/'comparison.png')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    render(parser.parse_args().directory)
