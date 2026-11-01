# 我们意念合一：图像与脑电音乐展示

当前交付将连续视频流、PL_KEY1 四页脑电音乐与全套暖金色界面成套发布。使用和安装见 [展示版说明](SIGNALS.md)，交付检查见 [界面与发布记录](report/presentation_verification_20261020.md)。历史板端逐帧版本及备份保持。

本扩展由 PL_KEY0 循环切换十种画面。PS_KEY0、PS_KEY1 保留原眼控开始和暂停功能；在图像画面按任一 PS 按键，会先退出图像画面。手机端“返回主页”也可退出。本次四页由 PL_KEY1 循环进入疲劳、情绪、脑电音乐联动和音乐音频分析；旧图像候选中的 KEY1 仍为空闲。流式 OV5640 模式在 HDMI 上全屏显示视频，状态接口保留模式和来源。正在标定或验证眼控时，先完成标定，或按 PS_KEY1 停止，再进入图像画面。

| 顺序 | 模式 | 视频源 | 处理位置 |
|---|---|---|---|
| 1 | 原图 | OV5640 | PL |
| 2 | 霓虹轮廓 | OV5640 | PL 像素流水线、Sobel 与渐变霓虹叠加 |
| 3 | 彩色拖影 | OV5640 | PL 帧差、衰减历史与彩色叠加 |
| 4 | 运动分析 | OV5640 | PL 帧差区域叠加 |
| 5 | 灰度 | OV5640 | PL 整数亮度 |
| 6 | 二值化 | OV5640 | PL 阈值 |
| 7 | 中值滤波 | OV5640 | PL 3×3 中值 |
| 8 | Sobel 边缘 | OV5640 | PL L1 梯度 |
| 9 | 直方图均衡 | OV5640 | PL 直方图及映射 |
| 10 | 瞳孔定位 | Tobii IS4 USB 灰度图 | PS OpenCV 眼区、轮廓及椭圆 |

OV5640 通过 VDMA0 的三缓冲、动态主从同步持续采集和显示，普通模式保持 1280×720。像素滤镜位于显示流上，每时钟接收一个像素，PS 只配置模式和读取状态，不复制、缩小或逐帧提交相机图像。拖影和运动分析在 320×180 的块网格上保存亮度历史，叠加于完整分辨率的视频背景。Sobel 和中值为因果 3×3 窗口，前两行、前两列保留灰度边界；均衡化用上一完整帧的直方图映射，首帧显示灰度。瞳孔检测保留 Tobii 的完整源图像，坐标单位为源图像像素。它显示检测候选，不参与注视标定或控制。没有可靠候选时不画圈。普通图像模式不会改用 Tobii，瞳孔模式也不会改用 OV5640。

切换模式和视频源会重置运动历史；输入失效时停止本次显示并恢复原 overlay，避免把旧视频当实时输入。图像模式继续读取原眼控协议状态，注视动作被屏蔽；退出后回到主页阅读状态。Tobii 缺图时显示等待；OV5640 启动失败或停流时报告错误并清理本次显示。真实运行不使用 CPU 滤镜替代 PL，也不使用演示图片替代摄像头。

## 文件

- `vision_demo/`：持续采集管理、模式配置、Tobii 画面、输入和资源归还。
- `hardware/vision_stream*`：连续像素滤镜、上一帧直方图和帧边界控制。
- `native/stream_ring.h`、`autonomous_capture.c`：连续视频环的启动、停止和原显示恢复。
- `hls/`：首版逐帧处理核及独立算例，供历史核对与回退。
- `native/`：连续视频库、历史 VDMA1 采集库及独立 Tobii 图像取流程序。
- `hardware/`：按键同步、引脚及联合工程连接脚本。
- `install_vision.py`：复用脑电演示包的停止态校验、成套安装和严格回退。
- `report/`：检查结果。预览图使用合成测试素材，图中有标识。

## 构建与预览

在工程根目录运行。使用已有 OpenCV 4、NumPy、Pillow；本机隔离环境为 `local/vision_tools`。CPU 合成效果图运行 `stream_preview.py`；`preview.py` 保留首版逐帧算法预览。

```powershell
$env:PYTHONPATH='integrations/vision_demo'
local/vision_tools/Scripts/python.exe -m unittest discover -s integrations/vision_demo/tests -v
local/vision_tools/Scripts/python.exe integrations/vision_demo/stream_preview.py --output integrations/vision_demo/report/stream-preview
python integrations/vision_demo/build_camera.py --stream --output integrations/vision_demo/build/stream_camera
local/vision_tools/Scripts/python.exe integrations/vision_demo/run_stream_sim.py --full --output local/vision_stream_sim_NEW
python integrations/vision_demo/build_stream_hardware.py --output local/vision_stream_hardware_NEW
```

工具脚本仅向子进程补齐 Windows 架构、DLL、Tcl 等环境，不修改 Vivado 安装。输出目录必须独立。工程保留原 HDMI、音频、VDMA 和 PS 配置，在原布局布线、时序、CDC、方法学与 DRC 检查之后生成 bit/hwh。

Tobii 图像程序需要已固定的 `ps_tobii/build/is4-probe.c` 和 `ps_tobii/third_party/njmill/LICENSE`，在 Z15 使用 `gcc -std=c11 -D_POSIX_C_SOURCE=200809L -O2 -Wall -Wextra -Werror tobii_images.c -o tobii-images $(pkg-config --cflags --libs libusb-1.0 openssl)` 编译。其主流程只订阅图像和恢复跟踪，不发送标定写入命令。

## 帧率与验收

配置的 HDMI 像素时钟为 75 MHz，总时序 1650×750；实际刷新率以板端计数为准。相机新帧率受相机当前时序、曝光和现场光照影响，必须单独实测。接口分别返回 `camera_fps`、`hdmi_hz` 和 `filter_pixels_per_second`，不把重复扫描同一帧计为相机新帧。瞳孔模式继续通过 Tobii USB 和 PS 获取图像、检测候选，其更新速度单独报告。

`board_stream_probe.py` 在停止显示、独占 PL 后运行九种模式，并让 PS 暂停两秒，核对硬件计数仍推进；结束后恢复已核验的原 overlay，之后才释放内存。用户当前不便接板，本轮实机项目保留待测。

## 安装与回退

板端沿用 PYNQ Python 3.8、OpenCV 4.2、NumPy、Pillow、libusb、OpenSSL、本地 Droid 中文字体及 `/usr/share/opencv4/haarcascades`。需要原综合控制台、正式脑电目录和共存眼控目录。无需重新烧录 S3、STM32，也不改蓝牙接线。

安装前先停止图像/媒体显示，确认该会话报告中的 `display_halted`、`buffers_released`、`original_restored` 全为 true。停止显示守护、媒体服务和正式采集服务后，运行预检；通过后再加 `--apply`。安装器和同目录的 `install_demo.py` 一同使用。

```bash
sudo /usr/local/share/pynq-venv/bin/python3 install_vision.py \
  --media-root /home/xilinx/gl-hdmi-live-20261008-ea117349 \
  --brain-root /home/xilinx/jupyter_notebooks/guardianloop_pynq \
  --eye-root /home/xilinx/brain_eye_coexist_20261005/eye \
  --bundle ./bundle
```

记下输出的 `INSTALLED_BACKUP`。安装会更新启动文件摘要、成对 bit/hwh 摘要和现有共存引用，保留原模型及控制配置。旧会话状态另存，历史报告保留。已安装首版的板卡，先用其原安装备份严格回退，再安装流式候选；安装器会拒绝直接覆盖未回退的扩展文件。重启原服务并进入静态主页后，按 PL_KEY0 测试。

回退前同样停止显示并验证资源已归还，停止上述服务，使用相同三个根目录和 `--rollback <INSTALLED_BACKUP>`。源文件或清单在安装后被再次修改时，回退会拒绝覆盖，需先核对修改。恢复服务后重新进入原静态主页。

## 来源

流式候选检查入口为 [修订记录](report/streaming_revision.md)。

本轮源代码与检查材料由 AI 辅助编写和整理。图像核为本工程新实现；HDMI、SCCB、GPIO 和 IS4 协议沿用工程已保留的来源。IS4 适配器保留 njmill 的 Apache-2.0 许可；OpenCV 使用板端已安装实现。真人图像只保存在忽略的本地检查目录，不放入公开交付包。

自检修订包：`GuardianLoop_Vision_Stream_20261019_r2.zip`，见 [自检记录](report/self_audit_20261019.md)。模式回执超过 0.6 秒、相机或 HDMI 停滞超过 1.5 秒分别报错。


## PL_KEY1 四页候选（2026-10-20）

见 [四页说明、预览与安装](SIGNALS.md)。音乐只有进入第三页后才由有效脑电结果选曲，四页内切换保持连续；退出停止。默认载入 LEMON 真实脑电记录，实时接入留待后续工程。音频 FFT 已与 Z15 连续图像/HDMI 输出一起构建，板端听音、同步与流畅度待测。
