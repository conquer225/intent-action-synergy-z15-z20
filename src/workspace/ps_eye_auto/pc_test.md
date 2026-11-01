# 在电脑上测试人脸与双眼模型

如果要测试左、中、右和三点校准，请使用旁边的 [PC_GAZE.md](PC_GAZE.md) 和 `start_pc_gaze.bat`。本文仍是只看人脸/双眼框的基础窗口说明。

无需 Z15、Vivado、串口或 SD 卡。此工具用板端同一份 `haar.c`、`auto_face.c` 和嵌入式模型常量，在 Windows x64 上运行。Python 负责读取照片/摄像头和显示结果，模型推理由 C DLL 执行。

## 这台电脑直接使用

1. 打开 `D:\fpga\z15_multimodal\ps_eye_auto`，双击 `start_pc_preview.bat`。
2. 出现“Z15 人脸与双眼模型 · 电脑测试”窗口。启动时不打开摄像头。
3. 点“打开照片”，选一张正脸照片。黄色框表示人脸，绿色框表示两只眼睛的分析区域。“找到双眼”才表示本次定位通过；“未找到可靠双眼对”时没有检测框。
4. 想实时测试，摄像头编号先填 `0`，点“启动摄像头”。保持正脸、两只眼睛可见，观察框是否落在眼睛上。若打开失败，关闭 Windows 相机/会议软件后再试；外接设备可试编号 `1`。
5. 点“停止”会清空结果并请求释放相机；切换照片也会停止采集。相机驱动阻塞时释放可能稍有延迟，等待停止状态后再开其他相机软件。关闭窗口结束程序。
6. 点“保存当前标框图”，选择保存路径。程序只在这次点击后保存图片，不自动录制摄像头。

旧照片在本机 `D:\fpga\z15_multimodal\local\eye_captures\auto_replay\inputs`，`raw.png` 是直接取图，另外两张是包含界面的截图。原先的 screen1/screen2 回归测试有裁剪显示区域；在窗口打开完整截图与裁剪后的结果可能不同。个人照片没有包含在发布 ZIP 中。

## 怎么判断效果

| 操作 | 观察内容 |
| --- | --- |
| 正脸，光线均匀 | 人脸框包住脸，两只小框分别在眼部 |
| 缓慢左右移动头 | 检测框重新定位，可能短暂丢失 |
| 遮住一只眼睛或离开画面 | 通常应失去可靠双眼对；若仍框住背景或遮挡物，记录为误检 |
| 戴眼镜、改变照明和距离 | 观察反光、欠曝、小脸造成的漏检或偏框 |
| 空白图、无人的背景 | 应不通过；出现框则是误检 |

这不是活体检测，照片上的人脸也会被识别。绿色框表示模型通过定位，不是暗区特征有效、瞳孔精确分割或眼控校准成功。当前基础窗口不输出 LEFT/CENTER/RIGHT；三点方向请打开 `start_pc_gaze.bat`。显示的 `PC 检测 xx ms` 只统计电脑上的 C 模型调用，不能代表完整摄像头延迟或 Cortex-A9 性能。

大图按比例缩到不超过 1280×720 再检测，窗口中显示的尺寸是送入模型的尺寸；显示缩放不改变检测坐标。小于 64 像素的图片会报错。

## 换电脑

使用独立包 `Z15_PS_Eye_PC_Test.zip`，解压到英文路径，安装 Windows x64 Python 3.11 或更新版本（带 tkinter）。打开终端进入解压后的 `ps_eye_auto`，运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r tests\requirements.txt
```

然后双击 `start_pc_preview.bat`。包内已带 `pc_runtime/model.dll`，无需 Vivado 或 GCC。摄像头使用 OpenCV VideoCapture，界面使用 Tk；`opencv-python-headless` 也可以读取摄像头。

修改模型或 C 检测源码后，程序会提示 DLL 与源码不一致。安装 MinGW x64 后重建：

```powershell
python tools\build_pc_model.py --gcc C:/mingw64/mingw64/bin/gcc.exe
```

无窗口运行一张图片：

```powershell
python tools\pc_preview.py --image D:/photos/face.png --output D:/photos/result.png
```

输出标框 PNG 和同名 JSON，JSON 含检测状态、框坐标和 PC 时间。窗口版本也可用 `--image` 在启动时打开指定照片。

本机检查：`python tests/test_pc_preview.py`。覆盖 C/Python 数据布局、真实照片回放、空白图、错误输入、Unicode 路径、旧结果丢弃、摄像头错误释放及 Tk 图像显示。摄像头错误用模拟设备验证；未替你开启真实摄像头。
