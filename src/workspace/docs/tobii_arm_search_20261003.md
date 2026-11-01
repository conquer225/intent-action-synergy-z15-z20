# Tobii OEM 模组直连 Z15：公开软件与协议检索

2026-10-04 实板更新：已用原生 USB/TTP 源码在该 Z15 的 ARMv7 Linux
取得实际图像与眼动包，厂家 ARMv7 运行库已不再是基础采集的必要前提。
完整校准、有效注视与稳定识别仍待验收，见
[实板记录](../ps_tobii/report/verification.md)。下面是移植前的检索结果。

检索日期：2026-10-03。目标实物：照片中的 `AP1QB000700 A00`，Dell 支架 `YW64G`，按 Alienware 17 R4/R5 拆机眼动组件、IS4 OEM 候选核查。目标主机：Z15 / Zynq-7015 Cortex-A9，ARMv7 32 位 Linux hard-float；运行与个人校准均不依赖电脑。

## 本轮判断

没有找到已验证兼容这块 OEM 模组、能直接部署到 Z15 的完整 ARMv7 Linux 软件栈。找到历史 Android ARM32 包的官方记录，也找到真正不调用 Tobii 闭源运行库的 USB 协议源码。后者目前明确支持 ET5，不能据此认定 IS4 OEM 兼容。

此前“取得匹配的 ARMv7 Linux 通信、注视和校准库后链路能成立”是工程条件判断，不是已有可下载包的事实。还需要满足设备接口、供电、固件、显示配置及校准恢复条件。本轮增加第二条可能路径：移植原生 USB 协议源码，补齐该 OEM 型号支持。它属于需要实物验证的开发任务。

## 公开候选

| 候选与来源 | 本轮核实内容 | 对本项目的含义 |
| --- | --- | --- |
| [Tobii Streams SDK](https://www.tobii.com/products/integration/tobii-streams-sdk) | 公开平台表的 Linux 为 x86-64；Windows / Android 列 ARMv8 64 位；型号能力需分别确认 | 没有公开列出 ARMv7 Linux |
| [Tobii Pro SDK](https://www.tobii.com/products/software/applications-and-developer-kits/tobii-pro-sdk) | 官网提供 ARM64 咨询入口；公开 Linux 表为 64 位 Ubuntu | ARM64 不等于 ARMv7，也不能直接推为 IS4 OEM 支持 |
| [历史 Gaze SDK / USB Service 下载统计](https://developer.tobii.com/devzonestats/downloads_by_platform.php) | Gaze C API 4.1.0 Android ARM32、USB Service 2.0.2 Android ARM32/64 曾存在 | 只有名称记录，未取得对应二进制和型号支持表 |
| [REX 固件说明](https://developer.tobii.com/rex-firmware/) | REX 历史支持 Android ARM32/64、Ubuntu；存在 USB-HID 与 USB-TCP/IP 固件区分 | 不能把旧 REX 支持移用到 IS4 OEM |
| [Eitol Linux 安装项目](https://github.com/Eitol/tobii_eye_tracker_linux_installer) | 作者明确测试 Ubuntu 18.10 x86-64、IS4/4C；包含配置校准工具 | 可供桌面 Linux 对照，不是 ARM 包 |
| [johngebbie 4C Linux](https://github.com/johngebbie/tobii_4C_for_linux) | 重包装上述库和 USB service 为 systemd；服务程序实际为 x86-64 ELF | 重新编译示例不能改变闭源库架构 |
| [cbasss Linux 安装项目](https://github.com/cbasss/Tobii-Eye-Tracker-Linux) | IS4/IS5 支持来自既有厂家栈与 Manager 修改；Arch 明确 `arch=('x86_64')`，Deb/RPM 同为桌面架构 | 没有底层 ARM32 源码或包 |
| [betaboon Python 封装](https://github.com/betaboon/python-tobii-stream-engine) | CFFI 调用 `libtobii_research.so` 中的 Stream Engine 接口，还要 USB Service | Python 封装未消除底层架构依赖 |
| [Tropaion/Tobii_Linux](https://github.com/Tropaion/Tobii_Linux) | Rust + rusb/libusb，直接 USB 读取注视点、设置显示区域、进行设备校准与保存恢复 | 当前最接近目标的协议参考，但只验证 ET5；未找到 ARMv7 实测 |
| [Aetherall/tobiifree](https://github.com/Aetherall/tobiifree) | Zig 协议核 + libusb daemon；支持表为 ET5 runtime `2104:0313`、bootloader `2104:0102`；有校准工具 | 可作协议交叉核查，IS4 OEM 未验证 |
| [njmill/tobii-linux](https://github.com/njmill/tobii-linux) | C/libusb/OpenSSL 的直接 USB/TTP 读取器，不调用厂家 `.so`；设备硬编码为 ET5 `2104:0313` | 适合参考较小的 C 通信层；其主机仿射校准不能自动替代设备内部校准 |

Tropaion 说明参考了 tobiifree，因此不能把它们当作相互独立的 IS4 兼容实测。开源源码存在意味着可以研究跨架构移植，不等于已在 Cortex-A9 编译或运行成功。较重的 GTK、游戏桥接、MediaPipe 也不应整体照搬到 Z15。

## 二进制检查

以只读方式获取公开文件，在内存中解析 tar 和 ELF，没有安装、执行驱动或运行库。ELF 文件头 offset 4 为位数，offset 18–19 为 `e_machine`。

| 实际读取的文件 | 字节数 | ELF 结果 |
| --- | --- | --- |
| [Eitol `stream_engine_linux_3.0.4.6031.tar.gz`](https://github.com/Eitol/tobii_eye_tracker_linux_installer/blob/62006d9bb11a848ed46fc57a0fdda12aba0be6c2/stream_engine_linux_3.0.4.6031.tar.gz) | 3,507,664 | `lib/x64` 库：ELF64 / machine 62，x86-64；`lib/x86` 库：ELF32 / machine 3，x86；未含 ARM |
| [cbasss `tobii-stream-engine-4.24.0-linux-x86_64.tar.gz`](https://github.com/cbasss/Tobii-Eye-Tracker-Linux/blob/ce064d152c64738abf0852d6598b3bead77df7a1/tobii-stream-engine-4.24.0-linux-x86_64.tar.gz) | 2,005,709 | `tobii-stream-engine-4.24.0/lib/libtobii_stream_engine.so`：ELF64 / machine 62，x86-64 |
| [johngebbie `tobiiusbserviced`](https://github.com/johngebbie/tobii_4C_for_linux/blob/20064bb363bdb11cdbc75994ca4526a3d644dd3d/tobii_usb_service/usr/local/sbin/tobiiusbserviced) | 28,753 | ELF64 / machine 62，x86-64 |

4.24.0 压缩包 SHA-256：`748b5008d2c091abb5e332ff76fa627f29d6acd73c1c85513343b8fa8158eb30`。USB 服务程序 SHA-256：`6fef508bce797a62053328f4bef9ca65d0a831d32948744887eb83354c916e13`。这些值记录此次所读文件，不是厂家签名或来源认证。

读取 [PyPI 官方包索引](https://pypi.org/pypi/tobii-research/json)：本轮查询版本为 2.1.0，最新 Linux wheel 是 `manylinux2014_x86_64`；返回的历史文件名中未发现 ARM/aarch 标记。此结果只覆盖该公开 Python 分发索引，不覆盖厂家按客户提供的包。

## 原生协议的具体边界

Tropaion 在提交 `71639383863fee69ff304efc5bb2173a6683896d` 的 [连接实现](https://github.com/Tropaion/Tobii_Linux/blob/71639383863fee69ff304efc5bb2173a6683896d/crates/tobii-usb/src/connection.rs) 中提供校准开始、采点、计算应用、取回和重新应用接口。[校准记录](https://github.com/Tropaion/Tobii_Linux/blob/71639383863fee69ff304efc5bb2173a6683896d/docs/wiki/Calibration.md) 也记录了早期“有 ACK 无效果”的操作码错误及后续修正。因此只读到函数名或成功 ACK 仍不足以验收校准。

其 [握手记录](https://github.com/Tropaion/Tobii_Linux/blob/71639383863fee69ff304efc5bb2173a6683896d/docs/wiki/Handshake.md) 承认 realm 响应解析存在错误，当前 ET5 无认证路径碰巧可用；认证路径只有单元测试，未上该硬件验证。IS4 OEM 是否使用相同握手、数据结构、认证及校准命令均未知。不能仅修改 VID/PID 后宣称支持。

njmill 提交 `4b231c3f3194047209a630f495416256a037175b` 的 [C 读取器](https://github.com/njmill/tobii-linux/blob/4b231c3f3194047209a630f495416256a037175b/tools/probes/tobii-ttp-mux.c) 直接调用 `libusb_bulk_transfer`，ET5 接口 0、IN `0x83`、OUT `0x05`。这些是 ET5 的代码常量，不是本实物的接线或端点信息。该项目 [主机校准实现](https://github.com/njmill/tobii-linux/blob/4b231c3f3194047209a630f495416256a037175b/scripts/recon/eye-pose-dashboard.py) 保存仿射修正，不能把它与厂家设备内完整个人校准等同。

tobiifree 提交 `ad82906a9c97f03be8bfcfeff9453198f6feb7a0` 的 [独立校准工具](https://github.com/Aetherall/tobiifree/blob/ad82906a9c97f03be8bfcfeff9453198f6feb7a0/applications/tobiifree-calibrate/README.md) 给出五点校准、保存、重新应用流程。固件刷写工具仍需要签名固件文件；本轮没有找到匹配 IS4 OEM 的可用固件。无需为了协议探测先刷写设备。

## HID 与拆机成功案例

[Microsoft GazeHid](https://github.com/MSREnable/GazeHid/blob/034a0bc24542ae5716eb2a4f9b687bf773eae1a8/drivers/tobii/tobii.c) 的 Tobii 示例调用 `tobii_api_create`、`tobii_device_create`、`tobii_gaze_point_subscribe`；[安装 INF](https://github.com/MSREnable/GazeHid/blob/034a0bc24542ae5716eb2a4f9b687bf773eae1a8/drivers/tobii/TobiiHid.inx) 复制 `tobii_stream_engine.dll`。这是一种 Windows 软件兼容层。设备管理器出现 HID 名称不能推出硬件原生输出 Eye/Head Tracker usage page `0x12`。需要实物 `report_descriptor` 才能判定。[Tobii Eye Control 说明](https://help.tobii.com/hc/en-us/articles/115002782614-Having-trouble-setting-up-Windows-Eye-Control) 同样要求先安装 Core 并校准。

找到 [Alienware OEM 改 USB 的作者实作帖](https://www.reddit.com/r/TobiiGaming/comments/16qj3mo/20_diy_tobii_eye_tracking_much_better_than_i_was/)：作者描述 Alienware 17 R4 拆机模组在 Windows 上改 USB 后完成眼动及校准，需处理软件对内置屏幕的判断。帖中其他用户补充 `XCMKD/033F74` 料号。它支持“同类组件有改装使用案例”这一线索，不是本实物、Z15 或 ARM Linux 的复现证据；帖子中针脚方向和线色不能直接用作本实物接线表。

## 后续验证顺序

1. 核对实物料号、线束与供电，然后读 USB VID/PID、速率、配置、接口、端点和 HID 报告描述符。这一步决定是否存在原生 HID 路径，或是否与已知 USB/TTP 模式接近。
2. 若是厂商 bulk 协议，先做最小枚举和只读设备信息查询。核对握手及注视数据结构，再决定使用 C 读取器还是 Rust 协议核；没有必要先部署 GTK 或游戏工具。
3. 取得带时间戳、有效标志的注视数据后，验证屏幕几何设置、个人校准、保存、断电冷启动恢复。任何环节仍需 PC 就不满足本任务要求。
4. 完成上述验证后才接入 Z15 左中右选区、停留确认与 HDMI。保留 r9 对照路径；屏幕注视点必须使用独立输入，不能填入现有摄像头瞳孔 Q8 坐标字段。

厂家查询入口为 [软件访问申请](https://developer.tobii.com/software-downloads-test/)。可询问：`AP1QB000700 / Alienware 17 R4 IS4 OEM` 是否提供 Cortex-A9 ARMv7 Linux hard-float 的 USB 通信、注视数据、显示配置和个人校准支持；若有，要求具体版本、ELF 架构、glibc/ABI、设备固件条件，以及校准保存恢复接口。本轮仅定位入口，未发送申请。

## 检索范围与限制

检索覆盖 Tobii/Dell 官方页面与历史下载记录、GitHub 安装包/源码、PyPI 分发文件、Windows HID 参考实现、ARM/Jetson 项目报告和拆机作者案例。查询包括 `Tobii armhf`、`Tobii armv7 Linux`、`IS4 ARM`、`tobiiusbservice arm`、`TobiiGazeSdk Android`、`AP1QB000700 Linux`、`XCMKD Tobii Linux`、`IS4 TTP protocol` 及中文眼动/树莓派检索。未记录到搜索结果不等于软件不存在。

还查询了 Wayback：旧下载页 2015-04-21 快照可读取，但未取得 ARM 包直链；`*android*` 的一项 CDX 查询为空，广泛 uploads 查询超时。没有将失败查询当作包不存在的证据。用户提供的知乎文章本轮仍无法读取，不根据标题推断内容。

资料由 AI 辅助检索和整理，原生协议来源另经来源核验代理逐文件检查。本报告区分官方声明、作者代码、单次二进制检查及工程推断。没有连接 Z15、编译 ARM 驱动、读取本实物 USB 描述符或执行真人校准；只有本报告与评估文档被修改。
