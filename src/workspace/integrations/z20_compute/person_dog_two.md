# Z20 视频文件与平板照片演示

适用实物为领航者 ATK-DF7010/7020P、XC7Z020 CLG400。源码位于 `z20_compute`，构建包为 `artifacts/person_dog_two.zip`。原有固定照片包保留。

## 视频文件

素材来自 Mixkit 的“A man walking his dog in the morning”，当前片段 6 秒、180 帧。原始发布页、公开镜像、许可和摘要保存在 `video/source.json`。`video/source.mp4` 保留下载文件，`video/playback.avi` 是 640×360、30 fps 的 MJPEG 兼容版本，转换信息见 `video/conversion.json`。原厂 OpenCV 3.4 缺少该 MP4 的解码插件，板端读取兼容文件。

`video/annotations.json` 保存人工复核的关键时间点。已有检测器辅助人物框，逆光下漏掉的狗框由人工登记。框位置随源时间戳插值，行为按片段登记为“人遛狗”；这是标注回放测试。后续识别模型通过同一结果接口接入。

人深度 Z、狗深度 Z 和两框中心的三维间距由 ARM 根据参考段计算。参考身高 1.70 m、犬肩部至爪尺寸 0.55 m、焦距 600 像素和主点 (320,240) 是本次测试先验，未在原拍摄现场测量。草地遮挡、姿态变化和参考尺寸误差会影响数值，画面按估算解释。距离公式与完整输入写入结果 JSON。

恢复既有专用 Linux、加载已核对的 CLG400 PL 后，进入包目录运行：

```sh
PYTHONPATH=. python3 -m z20_compute.person_dog_runner --root . --mode video --hdmi --output /tmp/person_dog_video.json
```

程序循环播放，Ctrl+C 退出。硬件不足以按源速度解码时会放慢播放，标注仍跟随源帧时间，不预设板端帧率。该模式独占原显示环，会停止摄像头写通道。

## 摄像头拍平板照片

将 `photos/scene0.png`、`scene1.png`、`scene2.png` 传到平板，全屏显示并切换。相机实际采集平板后，ORB 特征与 RANSAC 平面配准选择登记图，再把登记框映回当前帧；没有匹配或输入过期时清空结果。保持平板画面在相机视场中且有足够面积，避开强反光。

照片演示从每路 640×720 采集图按横纵各 4 抽样，旁路主视图为 160×180；在普通内存放大为 320×360 后配准和显示，保持原纵横比。实板上原横纵各 2 抽样复制约 79 ms，会跨过安全写入窗口，首轮未取得有效快照；各 4 抽样在独立采集检查中取得了有效帧。相机采集分辨率与原始环不变，此抽样入口用于照片演示，未绑定米制标定。

界面显示照片内容的人狗关系和图内估算间距。双目看到的是屏幕平面，摄像头到平板的米制距离另需与当前取景模式匹配的实测标定，当前保持待标定。

实时采集与叠加显示使用两个独立预留内存环。该模式要求新设备树 `hardware/navigator-camera-demo.dtb`：原相机环为 `0x01000000/8294400`，新增显示环为 `0x04000000/8294400`，由观察器 UIO map2 暴露。程序核对预留节点和映射，旧设备树下拒绝启用照片叠加显示。PL 仍用已有匹配固件。

临时引导时沿用 `NAVIGATOR_BOARD.md` 的 zImage、根文件系统和启动参数，只把设备树文件路径改为本包新文件。保持临时启动方式；设备树与 PL 不匹配时先停止验证。SD、eMMC 和 QSPI 的原启动文件无需替换。

加载匹配 PL 后，先按原记录设置 FCLK 和 PS-PL 复位，再首次初始化相机：

```sh
PYTHONPATH=. python3 -m z20_compute.person_dog_capture_start --root .
PYTHONPATH=. python3 -m z20_compute.person_dog_runner --root . --mode photos --hdmi --output /tmp/person_dog_camera.json
```

相机已运行时，初始化入口会拒绝再次启动。视频模式停止了采集后，重新进入照片模式应按原流程重新加载 PL 并初始化。相机中心裁剪模式有独立标识，旧标定不可沿用。

## 显示问题验收

此前实时 HDMI 多出窄分区，中心裁剪未解决。新的单主视图叠加使用独立显示环并关闭显示对采集环的 genlock 依赖，是待上板验证的替代显示路径。

先用静态诊断图检查 HDMI：

```sh
PYTHONPATH=. python3 -m z20_compute.person_dog_runner --root . --mode diagnostic --hdmi
```

应看到四块等宽色区、完整左右边框和圆形。此诊断占用原显示环并停止相机采集。再恢复相机、运行照片模式，检查主视图连续更新、有无回绕与多余窄条。寄存器无错误位不足以判定画面修复，须现场目视确认。

## 离线检查与后续

运行 `python build_native_person_dog.py`、`python build_camera_demo_dtb.py`、`python build_person_dog_two.py` 生成交付物。原厂根文件系统通过 `python build/qemu_person_dog_two.py` 验证原生库、照片配准、未知清空、兼容视频解码与叠加。`python -m unittest discover -s tests -p 'test_*.py'` 执行现有与新增测试。

实际执行结果见 `report/person_dog_two/verification.md`。恢复板卡后还需验证上传、显示窄分区、真实平板拍摄、相机连续性和端到端速度。通用分类与动作模型训练后续进行。
