# Z20 固定图片三分类

当前版本在电脑运行，登记一张人物照片、一张狗照片和一张草地背景照片。双击同目录的 `start_fixed_photo_demo.cmd`，左右方向键或空格切换，F11全屏，Esc退出。窗口使用1280×720画面；未来可把同一帧交给Z20的HDMI输出。板上按键与HDMI尚未接入本程序。

程序依赖NumPy、Pillow和Python自带的Tk。当前电脑已具备依赖；其他电脑可执行 `python -m pip install -r requirements-fixed-photo.txt`。字体默认使用Windows微软雅黑，也可通过 `--font` 指定中文字体。

## 记忆方式与实际结果

三张照片先缩为32×32灰度并做去均值和归一化，生成INT8模板权重，复用现有 `QuantizedMLP` 的1024→32 ReLU→3整数计算。标签顺序为人、狗、背景；当前只使用前三个隐藏节点完成模板相似度计算，其余隐藏节点权重为零。模型根据像素输出分数，切图顺序与文件名不参与分类。

这是固定图片模板记忆，未进行数据集训练。当前三张登记图的整数结果分别为 `[64,17,0]`、`[17,64,0]`、`[0,0,64]`，均命中对应类别。分数不是置信概率；这些结果是同图回忆结果，没有独立测试集。模型、像素预处理与实际PL接口可在后续板测时复用，当前backend为电脑软件整数参考。

图片和权重放在 `artifacts/fixed_photo_demo/`，结果与三张预览放在 `report/fixed_photo_demo/`。在本目录运行 `python build_fixed_photo_demo.py` 可从现有三张图片重新生成权重和预览。运行 `python -m z20_compute.fixed_photo_demo --export report/fixed_photo_demo` 只加载已保存权重并导出结果。

## 图片来源

原图按原文件保存，显示时仅等比例缩放。来源与SHA256同时保存在图库的 `sources.json`。

- 人物：NASA拍摄的Eileen Collins肖像，通过[scikit-image v0.25.2样例](https://scikit-image.org/docs/0.25.x/api/skimage.data.html#skimage.data.astronaut)取得；该页面说明为公有领域。
- 狗：Elf的“Yellow Labrador Looking”，通过[TensorFlow官方样例](https://www.tensorflow.org/tutorials/generative/style_transfer)取得；许可为[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)。狗的原图及展示中的照片部分保留这一署名与许可。
- 背景：scikit-image的grass样例；[官方说明](https://scikit-image.org/docs/0.25.x/api/skimage.data.html#skimage.data.grass)记载原素材来自DeviantArt，许可为CC0。此文件是该项目已裁剪、灰度化的样例，本次下载后未编辑原图。

代码和说明由AI辅助编写与检查，公开图片的作者及许可如上。
