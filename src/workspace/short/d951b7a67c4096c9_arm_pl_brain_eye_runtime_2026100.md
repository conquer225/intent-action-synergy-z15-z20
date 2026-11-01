# 脑控与眼控当前运行核对

核对日期：2026-10-05（客户端日期）。板端时钟为 2021 年，不能作为本次核对日期。
无线 SSH 为 `192.168.50.1`，本次启动 ID：
`810e96c1-6788-4bf6-939a-72e38787bfca`。
本轮只读，未修改板端文件、启动眼控、加载 PL、停启服务或重启。
逐文件哈希、启动记录及代码摘录见同目录 `ARM_PL_BRAIN_EYE_RUNTIME_20261005.json`。

## 已确认

脑控程序位于 SD 根分区的
`/home/xilinx/jupyter_notebooks/guardianloop_pynq/`。
当前发布 `guardianloop-fixed8-mobile-web-20261003`，48 个运行文件与安装清单
哈希全部一致。固定帽位保持 `F3,F4,C3,C4,T7,T8,O1,O2`。
采集服务 PID 700、网页服务 PID 699 均 active，NRestarts=0。
SSVEP/MI 后端分别监听 9105/9104，公开网页监听 9102。
本次启动自检 ready，情绪、疲劳、SEED、SSVEP、MI、滤波/质量路径均为 ARM。
MI 仍为实验模型，个人头和物理控制关闭；查询时 no_data，没有有效预测。

PL 当前通过 root 权限读取的 PYNQ 装载登记为
`/home/xilinx/jupyter_notebooks/guardianloop_pynq/guardianloop_pynq.bit`。
登记 IP 为 GuardianLoop registers、EEG quality、DE、HGB、AXI DMA、PS7。
本次启动记录的 PL ID 为 DE `44453031`、HGB `48473031`、model `50537911`；
启动记录同时明确 `used_by_current_cap=false`。
当前固定帽位的模型路径不能因此描述成已采用这些 PL 加速器。
普通 xilinx 用户的 PYNQ 查询返回空元数据，root 查询才返回正式加载登记；
没有据空结果判定 PL 未加载。本轮未发起 PL DMA 或主动寄存器读写。

眼控程序也在 SD 根分区，位置为 `/home/xilinx/tobii_z15/`，发现：

- ARM 源码：`src/hdmi_guide.py`、`src/calibration_worker.py`、`src/calibration.c`、
  `src/xds.py`、`src/selection.py`、媒体菜单等。
- ARM 可执行文件：`is4-calibration`、`is4-probe`，以及显示接口库 `libtobii_display.so`。
- PL 配套：`overlay/eye_wifi.bit`、`overlay/eye_wifi.hwh`。
- 启动入口：`start_local_media.sh`、`display_session.sh`；素材在 `media/`。
- USB 模组已枚举，视频设备名称为 `EyeChip: Tobii Video`。

当前没有发现 is4-calibration/is4-probe/眼控 HDMI 工作进程，没有眼控开机服务。
9090 的 Python 进程入口是 `/usr/local/bin/redirect_server`，不能当作眼控服务。
眼控源码通过 ARM 原生进程读取 Tobii USB 注视记录、完成方向校准/选择；
眼控 HWH 主要是 VDMA、VTC、DVI transmitter、live_osd 和视频接口，
不能把它描述为 PL 执行注视算法。

## 当前为什么不能直接完整同跑

眼控 `display_session.sh` 的已读取原文关键步骤为：

```sh
systemctl stop guardianloop-cyton.service || exit 1
if systemctl is-active --quiet guardianloop-cyton.service; then exit 1; fi
env XILINX_XRT=/usr "$python" -u "$program" "$@"
```

眼控 `src/hdmi_guide.py:112` 加载：

```python
overlay = Overlay(str(root/"overlay/eye_wifi.bit"))
```

退出时 `src/hdmi_guide.py:362` 用 `Overlay(original)` 恢复之前的完整设计，
包装脚本仅在恢复登记与原路径一致时重新启动原脑控服务。
因此现有完整眼控 HDMI 启动路径明确与脑控采集互斥，且替换整个 PL。
两份文件同时存在不等于两个独立完整比特流同时驻留。

## 推断、未验证和下一步边界

- 两套 ARM 算法可以设计成共存，但必须处理现有互斥启动流程、USB 使用、
  线程/进程负载以及控制命令仲裁；本轮没有验证眼控与脑控同场负载。
- 目前脑控固定帽位计算在 ARM，故不一定要先合并所有 PL 加速器；可评估保留
  一套显示 PL，并让两路 ARM 程序并行。是否会影响启动自检和其他硬件使用，
  必须在隔离候选中确认，不能直接删除脚本的保护逻辑或切换比特流。
- 若最终两边都需要各自 PL 模块，则需要可重建工程整合成一套完整设计或另有
  经验证的重配置方案；不能假设加载第二个完整 `.bit` 会保留第一个设计。
- 可读 SD 上的源码与 `.bit/.hwh`，不代表能从 PL 反读还原完整 RTL/Vivado 源码。
- 当前内存 available 约 741 MiB、swap 使用 0，但眼控未运行、脑控查询 no_data；
  这些数值不证明完整多模态负载能够实时同跑。
- 根分区及 /boot 均 rw；FAT 启动分区仍有未正常卸载提示，服务仍有
  NeedDaemonReload=yes。没有执行 fsck、daemon-reload 或修复。

应先获得“做脑控＋眼控共存修改”的明确授权，再备份两套程序，选定统一 PL
策略和一个控制仲裁入口，完成隔离同场测试；不能仅依据本轮核对宣布共存完成。
