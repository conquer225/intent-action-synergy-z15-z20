# Z15 离线交流与媒体首版

本模式接在已有三点方向标定之后。运行时只读 SD 卡素材，用板端 HDMI 和眼控操作；声音通过 ALSA 输出。首批素材是六句常用语、参考项目的前三首音乐和前两段视频。实现与验收记录见 [local_media_verification.md](report/local_media_verification.md)。

## 安装到当前 SD 卡系统

更新包是 `build/Z15_Local_Media_20261005.zip`，用于已经能运行 Tobii 选区的 `/home/xilinx/tobii_z15`。包内是 Python 程序、启动脚本、aplay 和素材，不包含启动镜像或 FPGA 文件。

先把 ZIP 传到板端 `/home/xilinx/`。电脑连到板卡现有的无线网段后，可以用 SCP：

```powershell
scp D:/fpga/z15_multimodal/ps_tobii/build/Z15_Local_Media_20261005.zip xilinx@192.168.50.1:/home/xilinx/
```

这里使用本次板端查到的无线地址；若网络配置改变，以板端 `ip -4 addr` 为准。传完即可断开电脑。素材最后位于 SD 卡的 Linux 分区，不需要运行时联网。Windows 通常只能直接看到 SD 卡的启动分区，不能把该分区误当成 `/home/xilinx`。更新包约165MB，本次 `/boot` 仅剩107MB，不能放进该启动分区；可经SCP或U盘中转，根分区剩余约18GB。

先退出正在运行的旧显示程序，再执行：

```sh
cd /home/xilinx/tobii_z15
mkdir -p local_media_backup
for name in hdmi_guide.py guide_render.py; do
    test -e local_media_backup/$name || cp src/$name local_media_backup/$name
done
unzip -o /home/xilinx/Z15_Local_Media_20261005.zip -d /home/xilinx/tobii_z15
chmod +x bin/aplay
sudo sh start_local_media.sh
```

更新包附有逐文件 SHA-256 `update_hashes.json`。本次板端完整素材已安装，288 个素材哈希全部核对通过；重标定修复也已部署。原显示程序备份在 `local_media_backup`，本次修复前的四个运行文件另存于 `recalibration_backup`。

## 操作

启动后显示准备页。短按 `PS_KEY0` 连接模组，进入距离检查页；先调整位置，看实时距离和左右眼检测比例。位置合适后再按一次 `PS_KEY0`，倒计时后依次看中央、左、右三个白点，方向标定通过后进入主页。主页左区句子发声，中区看视频，右区听音乐。

进入主页、句子页、音乐页或视频后，如果这一轮识别不准，短按 `PS_KEY0` 重新标定；暂停状态也可以使用。程序先停止媒体和上一轮眼动采样，显示“准备重新标定”，等旧采样进程退出后进入距离检查页。位置合适后再按 `PS_KEY0`，重新跟随中、左、右三个白点，成功后返回主页。等待期间按 `PS_KEY1` 可取消；如果旧进程超过 12 秒仍未退出，会显示失败原因，不会同时启动第二份采样程序。沿用原来的标定算法。

距离是模块报告的眼原点 Z 平均值，约每半秒更新，显示一位小数。数据超过 1.5 秒未刷新或没有有效距离时显示“距离未知”，不延用旧读数。位置检查、三点标定、选区验证及媒体菜单显示距离和眼部状态，视频上方保留实时距离。上一轮可用记录的三点距离约为 40.5、42.1、42.6 cm，界面用 40～43 cm 作参考；没有新增强制距离门槛。原生会话的 3 分钟时限包括位置调整和三点标定，调整后及时开始；超时后按 PS_KEY0 重新连接。

出现“本点可用方向数据不足”时，说明该点没有取得至少 60 个有效横向样本，或有效数据首末跨度不足 2 秒。先在距离检查页把模组对准双眼、保持头部稳定，再开始标定。眼睛被检出与注视有效是不同状态，单看距离或检出比例不能确认标定成功。本次具体失败数据见 [距离显示与排查记录](report/distance_display_1005.md)。

不要用整板 `RESET` 代替重标定。`RESET` 会重启 Linux，当前程序和内存里的标定结果随之结束，SD 卡文件保留。启动仍采用手动方式；复位后登录板端，再执行：

```sh
cd /home/xilinx/tobii_z15
sudo sh start_local_media.sh
```

出现准备页后按 `PS_KEY0` 检查距离，再按一次开始三点标定。如果在前台运行，保持这个终端连接；也可以用下面的后台方式启动，等准备页出现后断开电脑：

```sh
sudo sh -c 'nohup sh /home/xilinx/tobii_z15/start_local_media.sh > /home/xilinx/tobii_z15/local_media.log 2>&1 < /dev/null &'
```

每页左、中区显示两个条目，右区翻页；最后一页右区返回主页。进入新页有 1.2 秒阅读时间，然后按已有的停留进度选中。持续看刚刚选中的同一区域不会再次触发，先看另一区域才能继续选。

- 句子选中即播放一次，播放完仍留在句子页。
- 歌曲选中即进入播放页。左区播放时是停止，停止或播完后变为从头播放；中区下一首，右区返回列表。返回或切换会停止旧音频。
- 视频是 640×360、10 帧/秒、无声 JPEG 序列。播放中暂停眼控操作，USB 眼动仍持续接收；播完返回原列表页，`PS_KEY1` 可提前退出。
- 其他页面的 `PS_KEY1` 暂停或继续眼控。暂停会停止音频，继续后重新选择才会播放。

素材缺失、解码失败或声音设备不可用会显示原因。右区返回入口继续可用。

## 声音输出

包内 `bin/aplay` 来自 Ubuntu Focal 官方 ARM hard-float `alsa-utils`，已在当前 ARMv7 板上执行版本检查。来源、软件包与二进制哈希记录在 `bin/SOURCE.json`，许可证在 `bin/COPYRIGHT`。运行时优先用系统 aplay，没有时用该副本。

接好 Linux 支持的音频设备后，在板端检查：

```sh
cat /proc/asound/cards
/home/xilinx/tobii_z15/bin/aplay -l
```

默认 ALSA 设备是 `default`。若设备没有成为默认输出，用列表中的实际 CARD 名称：

```sh
sudo sh start_local_media.sh --audio-device 'plughw:CARD=Device,DEV=0'
```

`Device` 是示例，需换成实际声卡名。也可以修改 `media/playlist.json` 的 `audio_device`；修改后重新启动。当前没有接出声设备，实际听到六句话和音乐仍待验收。

本次查到原内核 `CONFIG_SND_USB_AUDIO` 未启用，已编译并成功加载匹配 `5.4.0-xilinx-v2020.2` 的四个模块。包内 `drivers` 保存模块、对应源代码包与构建来源，启动脚本会按需加载；没有更换内核或启动镜像。不同内核不能套用这些模块。可选的 `tools/build_usb_audio.sh` 用板上头文件副本离线重建，不改系统头文件；`tools/setup_usb_audio.sh` 可单独加载。

## 替换或重新准备素材

板端不做语音合成、格式转换或视频压缩。替换素材时在电脑上先转换，再复制到 SD 卡 `media` 目录并更新 `playlist.json`。显示文字与文件路径独立；文件名可用数字。配置示例：

```json
{
  "version": 1,
  "audio_device": "default",
  "speech": [{"label": "我需要喝水", "path": "speech/01.wav"}],
  "music": [{"label": "歌曲名称", "path": "music/01.wav"}],
  "videos": [{"label": "视频名称", "path": "videos/01", "fps": 10, "frames": 175}]
}
```

WAV 使用 16 位 PCM；音乐默认 44.1kHz 双声道。视频文件夹中按 `frame_000001.jpg`、`frame_000002.jpg` 连续编号，所有帧均为 640×360。帧数与配置一致。

本次素材通过参考项目现有的 Piper 模型与电脑 FFmpeg 生成。可使用参考项目已有虚拟环境重新生成：

```powershell
& 'D:/ai/WebcamGaze_Communication/WebcamGaze_Communication/WebcamGaze_Communication/.venv/Scripts/python.exe' ps_tobii/tools/prepare_media.py --reference 'D:/ai/WebcamGaze_Communication/WebcamGaze_Communication/WebcamGaze_Communication' --ffmpeg 'ps_tobii/build/pc_tools/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
python ps_tobii/tools/prepare_media.py --verify
python ps_tobii/tools/package_local_media.py
```

素材来源、原始文件哈希、语音模型及其原许可证说明保存在 `media/provenance.json`；成品哈希在 `media/hashes.json`。

## 检查与回退

电脑软件检查：`python -m unittest discover -s ps_tobii/tests -v`。`--verify` 会检查素材哈希、WAV 与所有 JPEG。

板端有限媒体检查使用 `media_smoke/speech/01.wav` 和真实第二段视频的 102 帧；本次小样本已通过串口部署。复制完整版后，也可让检查直接读取完整素材目录。测试不会开始人眼标定：

```sh
sudo sh display_session.sh media-check --hdmi
# 完整包已复制时：
sudo sh display_session.sh media-check --hdmi --samples /home/xilinx/tobii_z15/media
```

该检查报告实际视频耗时、已呈现/跳过帧、HDMI 计数和 ALSA 结果。它不能替代真人菜单测试或听音验收。

若要回到旧选区流程，退出媒体程序后仍可按原命令启动 `--relative-selection`。若需完全回退修改过的显示代码：

```sh
cd /home/xilinx/tobii_z15
cp local_media_backup/hdmi_guide.py src/hdmi_guide.py
cp local_media_backup/guide_render.py src/guide_render.py
```
