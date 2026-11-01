# Z15 无线眼控 r9 逐步使用指南

更新：2026-09-30。按当前交付包、板端检查器和电脑界面源码核对。

1）先看清目前做到了哪一步。

本版链路是：OV5640 采集 → 板端裁剪完整脸部 ROI → USB 无线网卡发给电脑 → 电脑定位双眼瞳孔 → 原摄像头坐标回传 → PS 三点校准、左中右判断、停留事件 → HDMI 叠加显示。

代码、配套 bit/hwh、ARM Linux 库、Windows 检测 DLL 和两个交付包已经生成。21 项 Python 检查、8 组 C 回归、RTL 仿真、ARM 编译和文件配套核验通过。历史照片回放修复了重裁剪造成的框漂移；这不等于真人准确率测试。

r9 尚未在你的 Z15 与 USB 网卡上实测。第一次运行需要确认现有 Linux 环境、网卡驱动、摄像头和 HDMI，然后做真人校准。本版输出左/中/右和停留事件，不会自动移动 Windows 鼠标，也没有接入灵巧手执行器。

2）准备这几样东西。

| 物品 | 本次用途 |
| --- | --- |
| Z15、原电源 | 运行板端程序 |
| 原 OV5640 | 接原来的 P2，沿用已出图的接线 |
| HDMI 显示器 | 接 Z15 HDMI 输出，用于看画面和校准白点 |
| 原 USB 无线网卡 | 接原来已能联网的 USB host 接口 |
| 以前能运行无线传输的完整 Linux/PYNQ SD 卡 | 启动板端系统，保留原驱动和无线配置 |
| Windows 电脑 | 接收 ROI、计算瞳孔、显示操作界面 |
| 板端终端 | 原来的 Linux 串口终端或可用的 SSH 登录 |

电脑和板卡应处于可以互相访问的局域网。电脑可以接同一路由器的 Wi-Fi 或有线网络。访客网络、客户端隔离会妨碍互通。

接相机、SD 卡和网卡时先断开板卡电源。相机朝向脸，先让整张脸和双眼清楚地进入画面；当前没有经过实测的固定最佳距离。

3）区分交付包与启动文件。

| 路径 | 怎么用 |
| --- | --- |
| `D:/fpga/Z15_Eye_WiFi_r9.zip` | 完整包，板端需要它 |
| `D:/fpga/Z15_Eye_WiFi_PC_r9.zip` | 仅电脑端包，换电脑时使用 |
| `D:/fpga/z15_multimodal/ps_eye_net` | 这台电脑已经存在的维护目录，可以直接运行电脑工具 |
| 完整包内 `linux/overlay/eye_wifi.bit`、`eye_wifi.hwh` | 板端程序自动加载，保持二者配套 |
| 完整包内 `linux/runtime/libeye_board.so` | ARM Linux 板端库，不是 Windows DLL |
| 完整包内 `pc_runtime/pupil.dll` | Windows 电脑检测库，不要放到板端运行 |
| 完整包内 `build/BOOT.BIN` | 有线裸机备用固件，本次无线 Linux 启动不用它 |
| 完整包内 `linux/boot_reference` | 原样保存的无线启动参考，不是完整 SD 镜像 |

不需要先打开 Vivado、下载 JTAG 或重新编译。无线版在 Linux 内动态加载 overlay。

不要格式化现有 Linux SD 卡，也不要把 `build/BOOT.BIN` 覆盖到它的启动分区。你给过的 BOOT、image.ub、boot.scr 等文件没有根文件系统；若手里只有这些文件、没有原来能启动的完整 Linux 卡，当前完整 ZIP 也不能替代完整系统镜像。若目前插的是 r8 裸机 SD 卡，应换回之前能运行无线传输的 Linux 卡。

4）先启动原 Linux 系统，找到板卡无线 IP。

打开原来使用的 Linux 终端，等到可以输入命令。使用原来的用户名和密码，不能根据启动文件猜登录信息。当前无线工具不使用旧版 PL UART 参数窗口，也不要求选择 COM 口；串口只可用作 Linux 登录入口。

在板端 Linux 终端输入：

```sh
whoami
uname -m
ip -4 -br addr
```

记下 `whoami` 给出的用户名，以及无线接口的名称、IPv4。ARM32 常见输出是 `armv7l`；预检查还会验证 Python 位数和系统 ABI。

例如：

```text
wlan0  UP  192.168.1.123/24
```

这里 `wlan0` 是接口名，`192.168.1.123` 是板卡 IP。后面的 `/24` 不要输入电脑工具。以上只是示例，用你的实际值。

若 `ip -4 -br addr` 不支持简写，运行 `ip -4 addr`。若没有无线接口，先检查原 USB 网卡和驱动；若有接口但没有 IPv4，用原来已经成功过的方法连接无线网络。眼控程序不会替你安装网卡驱动或修改 Wi-Fi 密码。

如果原系统使用 NetworkManager，可先运行 `command -v nmcli` 和 `nmcli device status` 确认工具存在、无线接口受它管理。尚未联网时，在板端本地终端执行以下命令，接口名和网络名都换成实际值：

```sh
nmcli device wifi list ifname wlan0
sudo nmcli --ask device wifi connect "你的Wi-Fi名称" ifname wlan0
ip -4 -br addr
```

`--ask` 会交互询问密码，不必把密码写在命令中；该连接操作只在需要联网时手动执行。如果 NetworkManager 不存在或接口显示 unmanaged，沿用原镜像的连接方式，不要为了本指南切换网络管理器。命令依据 [NetworkManager 官方 nmcli 手册](https://networkmanager.dev/docs/api/latest/nmcli.html)。

5）把完整包传到板端主目录。

这台 Windows 电脑已存在 `ssh`、`scp`。板端 SSH 已启用时，打开 Windows PowerShell，逐条执行：

```powershell
$BoardIP = Read-Host '输入板端无线 IPv4'
$BoardUser = Read-Host '输入板端 Linux 用户名'
ssh "${BoardUser}@${BoardIP}"
```

如果首次连接提示主机指纹，核对目标确实是这块板卡后再接受。输入原 Linux 密码时终端不回显字符，这是正常行为。登录成功后可以运行 `whoami`，再输入 `exit` 回到 Windows。

在同一个 PowerShell 里传包：

```powershell
scp 'D:\fpga\Z15_Eye_WiFi_r9.zip' "${BoardUser}@${BoardIP}:~/"
```

这会把完整 ZIP 传到该用户的 Linux 主目录。若使用另一台电脑，把本地 ZIP 路径改成它实际所在位置。

SSH 不可用时，可以沿用原来的文件传输方式。也可先正常关闭板端系统、断电，将 ZIP 复制到现有 SD 卡 Windows 可见分区，再插回启动；只复制 ZIP，不替换启动文件，不格式化 Windows 无法识别的 Linux 分区。Linux 下挂载路径因系统而异，先找实际文件位置，再解压。

6）在板端解压完整包。

以下命令在板端 Linux 终端执行：

```sh
cd ~
ls -lh Z15_Eye_WiFi_r9.zip
python3 -m zipfile -e Z15_Eye_WiFi_r9.zip .
cd ~/ps_eye_net
ls linux/overlay/eye_wifi.bit linux/overlay/eye_wifi.hwh linux/runtime/libeye_board.so
```

最后一条应列出三个文件，不应报 `No such file`。从 SD 可见分区传包时，第二、三条中的 ZIP 路径要替换为实际挂载路径；解压目标仍可使用主目录。

如果板端已有旧 `ps_eye_net`，先停止旧服务、备份旧目录，再解压到干净目录，避免新旧文件混用。不要只复制 `.so` 或 `.bit`：运行库会核对源码哈希。

7）检查板端环境，通过后才启动眼控。

先停止原来运行的相机、HDMI、VDMA 和其他 overlay 程序；Jupyter 中使用这些硬件的代码也应停止并释放资源。避免两个程序争用同一套 PL。

确认位于主目录下的 `ps_eye_net`，把下一条的 `wlan0` 换成第4步查到的接口：

```sh
cd ~/ps_eye_net
WIFI_IF=wlan0
sudo python3 linux/check_environment.py --interface "$WIFI_IF" --probe-cma --report board_environment.json
```

检查会输出 JSON。正常结果末尾包含：

```json
"ready": true
```

各项检查的 `ok` 应为 `true`。重点是 ARMv7 Linux、numpy、cv2、pynq、ARM 库、HWH 地址、已联网无线 IPv4、USB host、独占视频寄存器和五块 CMA 图像内存。CMA 探测只临时申请再释放，不启动 DMA；本步骤也不下载 bitstream。

如果是 `"ready": false`，找到 `"ok": false` 的项，读它的 `name` 和 `detail`。先处理该项，不能仅因为文件解压成功就跳过环境检查。报告保存在 `~/ps_eye_net/board_environment.json`。

8）启动板端服务，并保存日志。

预检查通过后，保持同一个 Linux 终端：

```sh
sudo sh linux/start_board.sh --interface "$WIFI_IF" 2>&1 | tee board_run.log
```

启动器会再检查一次环境，然后加载配套 overlay、初始化 OV5640 和视频通道。成功后日志中包含：

```text
Z15_EYE_WIFI_READY interface=wlan0 ip=192.168.1.123 port=5001 codec=JPEG95
```

此处会显示实际接口和 IP。HDMI 应开始显示相机画面；在电脑未连接前来源可为本地检测。保持这个终端和服务运行，不要关闭 SSH 窗口。

如果还没出现 READY 就报错，先查板端错误，电脑界面无法替代相机/视频启动。若出现 READY 后又报采集超时，服务也没有正常持续运行，应保留前后日志。

9）在 Windows 启动电脑端。

这台电脑已核对为64位 Python，numpy、OpenCV、Tk 均能导入，可以直接使用现有目录。打开新的 Windows PowerShell：

```powershell
cd D:\fpga\z15_multimodal\ps_eye_net
python -c "import struct,numpy,cv2,tkinter; print('Python bits:',struct.calcsize('P')*8); print('dependencies OK')"
```

应显示 `Python bits: 64` 和 `dependencies OK`。

换电脑时，先解压电脑端包，进入里面的 `ps_eye_net` 目录；使用64位 Python，执行：

若尚未安装 Python，按 [Python 官方 Windows 使用说明](https://docs.python.org/3/using/windows.html) 安装并确认终端中的 `python` 可用，再执行下面的依赖安装。这台电脑已经具备运行环境，无需重装。

```powershell
python -m pip install -r tools/requirements.txt
```

启动界面，下一条的 IP 换成板端 READY 日志中的实际地址：

```powershell
python -u tools/net_monitor.py --board 192.168.1.123
```

也可以双击目录中的 `start_pc_net.bat`，输入同一个 IP 后回车。不要直接使用脚本的默认地址，除非板卡实际就是那个地址。

出现 Windows 网络访问提示时，允许程序访问正在使用的私有局域网。窗口标题应为 `Z15 无线眼控 · 脸部 ROI / 瞳孔回传 r9`，不是旧串口工具。

10）先确认传图和坐标回传，再校准。

正常界面先显示“全帧找脸”，找到人脸后显示“完整脸部 ROI”。检测丢失时可能重新进入全帧搜索，这属于恢复流程。图像来自板端 OV5640，不是电脑摄像头。

| 界面信息 | 怎样判断 |
| --- | --- |
| 来源 `PC` | 板端正在使用电脑回传特征 |
| 板端帧、已回传帧增加 | 图像和电脑计算链路在运行 |
| 双眼 `[1, 1]` | 两眼特征当前有效，可开始校准 |
| 绿色分析框、黄色十字 | 当前有效眼区及检测瞳孔位置；还要目视检查是否落在真实眼睛上 |
| 相机/HDMI 帧计数增加 | 对应视频通道持续运行 |
| 校准“未开始” | 尚未完成人体校准，不能仅凭瞳孔坐标就要求正确左右方向 |
| 有效为0、方向无效 | 校准前或特征不满足时可能出现，并不直接表示 UDP 没通 |

头先保持稳定，整张脸不要靠裁剪窗口边缘。调整脸的位置和光照，让双眼连续有效；避开强背光、镜片反光或睫毛遮挡。当前效果以实际预览为准。

按钮可点击不等于双眼已经持续稳定。首次校准先确认来源为 PC、双眼连续有效、画面持续更新。板端日志中应能看到 `NET_PEER` 和来源切换信息。

11）完成左、中、右三点校准。

点击“开始三点校准（看 HDMI）”，先看控制回执是否“已接受”。若拒绝，等脸和眼睛稳定后再试，不要连续点击。

接下来按 HDMI 白点的位置看，不要盯着电脑预览：

- 白点在左侧：头保持不动，眼睛看左侧白点，直到白点切到中间。
- 白点在中间：看中间白点，直到切到右侧。
- 白点在右侧：看右侧白点，直到电脑状态显示校准“已完成”。

每个点先累计2秒稳定等待，再为两眼分别收集16个有效样本。实际耗时取决于有效帧间隔，不能只数2秒就主动换点。以白点和“看左点/看中点/看右点”状态为准。样本 `counts` 会增加，并在换点时重新累计。

短暂眨眼或单眼失效会暂停该眼采样并保留已有进度。头部大幅改变、网络超时、双眼无效会妨碍继续采样。

若出现“失败，请重试该点”，先改善画面或坐姿，再点“重试失败点”。程序会回到需要重采的目标点，不要自行假定总是重做右点。想从头开始时，点“清除校准”，等板端接受，再点开始。

点击开始后整个过程中尽量不要移动头、改变座位或把眼睛转到电脑屏幕。移动较大或来源切换后，需要重新校准。

12）验证实际眼控事件。

校准完成后，先看中间，再执行以下顺序：

- 看左侧并保持。状态应转为左；达到停留条件后事件计数增加一次。
- 继续看左侧，事件不应连续增加。
- 看中间，至少保持350 ms并等状态稳定回中。
- 看右侧并保持。状态应转为右；达到停留条件后再增加一次事件。

侧向停留门槛为750 ms，滤波、方向稳定和有效帧还会增加实际响应时间。测试时先保持约1～2秒，不要用短促扫视判断是否失效。

板端日志会出现类似：

```text
EYE_EVENT seq=1 direction=1 source=PC
EYE_EVENT seq=2 direction=3 source=PC
```

数字方向为0无效、1左、2中、3右；日志时间和序号以实际运行结果为准。左/右停留确认才是当前动作事件。事件增加不会自动驱动灵巧手或电脑鼠标。

13）知道断线和超时会发生什么。

超过220 ms的电脑回传、旧会话/旧帧、越界结果不进入动作判断。连续三次无有效回传会回到 PS 本地检测；电脑握手消失1.5秒也会触发本地回退。恢复时用独立探测，收到合格回传才切回 PC；来源切换会清除旧校准，需要重新做三点。

本地回退不是无线主链路验收成功，ARM 本地计算仍有运行时间限制。若来源反复在 PC/LOCAL 间变化，先解决传输或计算超时，不要反复校准。

界面显示“图像已过期”时，保留的图像不代表当前瞳孔；状态过期时按钮会禁用。一次只运行一个电脑接收器，不要同时启动两个窗口或 GUI 与 headless 模式。

14）正常停止，下次如何重开。

先关闭电脑界面，再在板端运行服务的终端按 Ctrl+C。等板端显示 `Stopping eye control` 并返回 shell 提示符；程序会先停止 DMA 再释放图像内存。不要用强制杀进程代替正常退出。

下次使用，在板端 `cd ~/ps_eye_net` 后重新执行第8步，在电脑端重新执行第9步，再校准。重新运行时也检查板卡实际 IP，DHCP 地址可能变化。

需要关闭板卡时，服务退出后执行 `sudo shutdown -h now`，等系统关机完成再断电。回到旧版时使用此前保留的配套 SD 卡/启动环境，不混用新旧 bit、hwh、运行库和源码。

15）遇到问题按现象定位。

| 现象 | 先查什么 / 怎么处理 |
| --- | --- |
| 只有裸机串口日志，没有 Linux 命令行 | 很可能仍是 r8 裸机启动卡；使用以前的完整无线 Linux 卡 |
| 没有无线接口或没有 IPv4 | 原网卡是否插在正确 host 口、原驱动是否加载、原无线连接是否成功；这些不由眼控服务配置 |
| `ModuleNotFoundError` | 在运行服务的同一个 Python 中检查模块；电脑端装 requirements，板端沿用原 PYNQ 环境 |
| 普通用户能导入 pynq，sudo 却不能 | sudo 使用了不同 Python；先用下面的“指定同一解释器”命令检查和启动 |
| ARM 库 ABI/glibc 失败 | 需要兼容 ARM32 hard-float 的 Linux/Python 环境；保留完整错误，不能把 Windows DLL 当替代品 |
| 哈希不匹配、要求重建库 | 停止运行，重新完整解压匹配的发布包；不要删掉校验或混用旧 C 源码 |
| 五块 CMA 申请失败 | 停止旧视频/overlay 程序，检查报告的 CMA 内存；持续失败需核对现有 Linux 内存配置，不能单靠复制 bit 解决 |
| 独占视频寄存器检查失败 | 报告会列出占用驱动；需要核对原系统设备树和驱动占用，先不要手动解绑未知驱动 |
| `OV5640 initialization failed` | 断电后核对原 P2 接线、相机方向、供电；保存日志后再重启 |
| `VDMA startup failed`、采集/HDMI 停顿 | 查相机与视频状态、配套 bit/hwh 和前面的完整启动日志 |
| 服务锁失败或地址端口已占用 | 关闭旧服务/旧窗口，按正常退出流程释放；不要重复启动多份 |
| 电脑一直等板卡 | 核对实际无线 IP、板端 READY 和服务是否仍运行、网络隔离、防火墙及 UDP5001 |
| 有图但来源反复 LOCAL | 看超时、拒收、缺包和 PC计算时间；先恢复稳定 PC 回传 |
| 有脸但双眼经常无效 | 先改善脸部大小、光照、清晰度、镜片反光和头位；绿色框仍需目视确认 |
| 点校准被拒绝 | 看控制回执、最新双眼和稳定状态；等新有效测量后再发送 |
| 校准样本不增长或失败 | 看双眼有效、样本、参考和超时；先改善输入，再重试失败点 |
| 有图、有瞳孔，但没有左右事件 | 确认校准完成、状态有效，并测试“侧向停留→回中→另一侧停留” |

指定同一解释器：在已能导入 PYNQ 的板端终端执行，接口仍用实际值：

```sh
cd ~/ps_eye_net
PYTHON_BIN="$(command -v python3)"
sudo "$PYTHON_BIN" linux/check_environment.py --interface "$WIFI_IF" --probe-cma --report board_environment.json
```

检查通过后，用同一解释器直接启动服务并保存日志：

```sh
sudo "$PYTHON_BIN" -u linux/board_service.py --interface "$WIFI_IF" 2>&1 | tee board_run.log
```

PC本地 UDP5001被其他程序占用时，先关闭旧眼控窗口；确需另用端口时：

```powershell
python tools/net_monitor.py --board 192.168.1.123 --local-port 5002
```

板端仍使用5001，回传会发送到新握手的电脑端口；电脑防火墙应允许所用端口。`ping` 能通只是基础检查，不代表 UDP 图像已通；ping 不通也可能只是 ICMP 被拦截。

16）首次运行保留证据，便于继续定位。

保存板端 `board_environment.json`、`board_run.log`，以及电脑界面截图。截图应包含来源、双眼有效、校准状态、样本/参考、超时/拒收、相机/HDMI帧计数和预览。

需要详细电脑状态日志时，先关闭 GUI，回到电脑端目录再运行：

```powershell
python -u tools/net_monitor.py --board 192.168.1.123 --headless 2>&1 | Tee-Object -FilePath pc_status.log
```

这个模式持续记录 FRAME 和状态字典，不显示图像窗口，也没有校准按钮。用 Ctrl+C 停止；它重新建立会话，会影响原校准，结束后重开 GUI 并重新校准。

校准失败时，状态字段 `error` 为1表示三点分离不足，2表示三点顺序不一致，3表示噪声过大；`retry` 表示需要重采的点。不要只保存“失败”二字，保留该次状态、`refs` 和日志。

第一次验证按“Linux正常启动→无线有IP→预检查ready→板端READY和HDMI→电脑持续图像且来源PC→三点已完成→左右停留事件”的顺序记录。哪一步失败就先查那一步，不把后续现象当成前一步已经成功。

实现与验证记录：`D:/fpga/z15_multimodal/ps_eye_net/report/verification.md`。维护入口：`D:/fpga/z15_multimodal/ps_eye_net/README.md`。
