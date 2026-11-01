"""Create an ARMv7-ready fixed person-dog demo bundle and ZIP."""
import hashlib
import json
from pathlib import Path
import shutil
from zipfile import ZipFile, ZIP_DEFLATED

from z20_compute.fixed_scene_package import build_package


SOURCES = ('__init__.py', 'npu.py', 'backend.py', 'linux.py', 'fixed_scene.py', 'fixed_scene_depth.py',
           'fixed_scene_package.py', 'fixed_scene_hdmi.py', 'fixed_scene_keys.py',
           'fixed_scene_board.py')


def write_sha256_manifest(root):
    """Hash payload files without adding the manifest to its own listing."""
    files = sorted(p for p in root.rglob('*')
                   if p.is_file() and p != root / 'SHA256.json')
    listing = {str(p.relative_to(root)).replace('\\', '/'):
               hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (root / 'SHA256.json').write_text(json.dumps(listing, indent=2), encoding='utf-8')
    return listing


def main():
    here = Path(__file__).resolve().parent
    output = here / 'artifacts' / 'person_dog_board'
    bundle = output / 'bundle'
    manifest = build_package(here / 'artifacts' / 'person_dog', bundle)
    package = output / 'z20_compute'
    package.mkdir(parents=True, exist_ok=True)
    for name in SOURCES:
        shutil.copyfile(here / 'z20_compute' / name, package / name)
    readme = '''# 领航者 Z20 人狗固定场景演示

适用板卡：ATK-DF7010/7020P，XC7Z020 CLG400。先按工程的 NAVIGATOR_BOARD.md 恢复专用 Linux、加载匹配 PL，并核对四个 UIO 设备。当前包只登记三张人狗同框图。

进入本目录，运行：

```sh
PYTHONPATH=. python3 -m z20_compute.fixed_scene_board --bundle bundle --backend pl --hdmi --auto-seconds 4 --output /tmp/person_dog_result.json
```

按键切换：将 `--auto-seconds 4` 改为 `--keys`，PS_KEY1 上一张、PS_KEY2 下一张，Ctrl+C 退出。串口手动切换：删除 `--auto-seconds 4`，输入 `n` 下一张、`p` 上一张、`q` 退出。软件整数对照可将 `--backend pl` 改为 `--backend ps`。诊断时删除 `--hdmi`，只打印推理结果。

`--hdmi` 会停止相机 VDMA 写通道，占用预留视频环并启动 1280×720 显示。该模式与实时双目采集互斥；退出后重新加载 PL 并运行原相机启动程序可恢复双目。HDMI 寄存器计划来自本机领航者例程 38 和 Xilinx 2023.1 VTC／VDMA 驱动。PS_KEY1／2 对应原厂设备树中的 PS GPIO12／11，当前专用设备树删除了按键节点，所以程序直接读取 GPIO。实物屏幕出图、色序和按键仍待上板核对。

演示结果由输入 RGB 像素经 1024→32→3 INT8 模型选出场景；人狗框和“抱着／摸／牵着”是逐张人工核对的登记标注。左右位置由两个框中心计算。包内 `manifest.json` 校验模型、原始 RGB 输入和 HDMI 帧。这个实验的验收范围是包内三张照片。

新增深度 Z 和人狗中心间距由 `gallery.json` 中的参考段像素、参考尺寸及相机参数计算。使用 Z=fL/l 估算深度，再把框中心反投影成三维点并计算欧氏间距；参考尺寸和焦距由用户授权选取，结果标为 estimated。画面显示“人狗中心间距（估算）”，原始输入参数和三维点保存在 JSON 的 geometry 内。该间距以两个框中心为端点，接触面间隙需要另设端点。

照片来源和作者见 `bundle/sources.json`：美国国家公园管理局照片、美国海军 Christopher S. Harte 照片、Clem Onojeghuo 的 CC0 照片。文件名、原图 SHA256 和 Commons 页面逐项保留；演示图由原图按比例填充到 640×480。
'''
    (output / 'README.md').write_text(readme, encoding='utf-8')
    listing = write_sha256_manifest(output)
    archive = here / 'artifacts' / 'person_dog_board.zip'
    with ZipFile(archive, 'w', ZIP_DEFLATED) as z:
        for path in sorted(p for p in output.rglob('*') if p.is_file()):
            z.write(path, str(path.relative_to(output)).replace('\\', '/'))
    print(json.dumps(dict(archive=str(archive), sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                          registered_images=3, files=len(listing), bundle_files=len(manifest['files'])),
                     indent=2))


if __name__ == '__main__':
    main()
