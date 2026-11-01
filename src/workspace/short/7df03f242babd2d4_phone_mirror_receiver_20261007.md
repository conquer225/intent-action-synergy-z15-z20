# 手机无线投屏接收器：隔离编译与发现测试（2026-10-07）

## 本轮结论

MiracleCast 接收器已在 Z15 ARM 上成功编译。必要的 GStreamer 元件可加载，内存接收程序的合成图像自检取得 8/8 帧。实际手机投屏尚未通过：第二轮板端发现名为 `QqqQ`、厂商字段为 `ohos` 的 Wi-Fi Display 源设备，用户报告手机未搜到 `GuardianLoop-Cast`。第三轮已在用户关闭手机个人热点、保留移动数据并打开投屏搜索后完成；板端再次发现该手机，但没有成组或视频会话记录。用户随后明确确认第三轮仍未搜到接收器，并提供无线投屏搜索截图。没有验证 P2P 成组、RTSP 连接、手机视频解码或 HDMI 显示，不能把编译、自检或单向发现写成投屏成功。

当前已经恢复原 `GuardianLoop-Z15` 热点（AP、192.168.50.1/24）。有线地址仍为 192.168.2.99。正式网页 HTTP 200；网页、采集及 NetworkManager 的 PID 与重启次数均与本轮开始时相同。受保护的 8 项配置/启动/发布清单 SHA256 校验一致。

## 范围及来源

用户授权下载、编译接收器、补齐用户态依赖和临时独占无线网卡。未执行 apt 安装/升级、内核或驱动替换、PL 加载、JTAG、板卡重启、启动镜像改写或正式 EEG 程序改动。

开源上游：https://github.com/albfan/miraclecast ，固定提交 `0b7f1f1f6586dc65ff480f3cda5c2170a70aa020`。上游源码没有修改；适配在本项目的隔离启动控制脚本中。

Ubuntu focal armhf 包来自 https://ports.ubuntu.com/ ，按官方 Packages 元数据校验大小及 SHA256，解包到用户目录，未运行包安装维护脚本。没有单独完成 Release 签名校验，不宣称完成 GPG 供应链验证。开发库与板端 systemd 245.4-4ubuntu3 及 FFmpeg 4.2.2-1ubuntu1 对齐。解码插件只通过隔离环境变量及链接目录加载，未放入全局插件目录。

板端目录：`/home/xilinx/gl-mirror-20261007-000905`。本地代码、依赖清单、构建日志及测试记录：`D:/ican/codex_project/mirror_receiver_20261007/`。

## 已完成的验证

四个 ARM 可执行程序构建成功，并执行帮助/动态链接检查：miracle-wifid、miracle-sinkctl、miracle-wifictl、miracle-dhcp。

隔离 GStreamer 元件检查通过：tsdemux、h264parse、avdec_h264、appsink、videoconvert。合成图像测试只是 videotestsrc → BGR → appsink，不包含 H264、RTP、无线网络或真实手机画面。

第一轮启动过早请求 P2P 扫描，出现 Invalid argument；服务退出后执行回退。第二轮调整等待/重试后，P2PScanning=1，WFD 接收端信息已交给 wpa_supplicant。无线日志记录到手机 QqqQ 的设备发现及源端 WFD 子元素，但没有实际连接事件。

同时发现上游默认配对方法字符串 `pbc` 在现有 wpa_supplicant 中未形成有效的 WPS 方法声明（日志 Config Methods 为 0）。临时执行 SET config_methods push_button 返回 OK；控制脚本下一轮改为从启动时声明 push_button。仅凭此修正还不能判定手机搜不到的原因已经解决。

第三轮已使用 `push_button` 配对声明。控制接口读回 WFD 接收端子元素，状态含 `wifi_display=1`；日志记录一次 P2P-DEVICE-FOUND，未记录 P2P-GO-NEG-SUCCESS 或 P2P-GROUP-STARTED。窗口末段另执行一次有界 P2P listen，返回 OK，仍没有会话记录。这些是软件控制/日志证据，不是空中抓包，不能据此认定广播帧一定到达手机，也不能单独归因于手机或网卡驱动。第三轮到时自动退出，恢复日志无失败项。

恢复脚本曾在重复回退时对“已运行”的 AP 刷掉地址，而 start 不会重新执行启动前置步骤；已修正为完整状态正常时不再刷地址，异常时先停止 AP/DHCP 再恢复，并核查地址和 AP 类型。对应两项回归测试在电脑和板端均通过。实际恢复核对通过。

## 网络含义及下一轮

Z15 加入手机个人热点是普通 LAN；MiracleCast 路线让手机选择 Z15 作为显示接收器，随后通过 Wi-Fi Direct 建立投屏连接。它们不是同一项操作。当前 USB 0bda:8179 / 8188eu 网卡声明 managed/AP/P2P-client/P2P-GO，但 iw list 未声明支持接口并发组合，因此没有承诺热点连接、P2P 投屏和互联网共享可同时保持。

关闭手机热点的对照已经完成，用户确认手机仍未搜到接收器。由于第三轮也修改了配对声明，不能把结果当成仅改变热点状态的单因素试验；可以确认关闭热点并修正声明仍不足以使这一组合被手机发现。故障停在发现/连接阶段，尚未进入视频传输，不能据此认定 130M 带宽或解码速度不足。测试已结束，当前不再广播 `GuardianLoop-Cast`；原 Z15 热点已恢复，手机个人热点仍按用户操作处于关闭状态。后续应继续限定在发现/协议兼容性诊断，或评估同 LAN 的显式录屏发送方案；不要用更大网卡速率冒充协议兼容性解决。没有决定最终架构必须关闭手机热点，也没有证明这块网卡能同时维持热点连接和 P2P 投屏。

每个测试窗口约 4 分钟，另有 RuntimeMaxSec 和独立回退定时器。只停止原 AP/DHCP，不停止整个 NetworkManager；接收器使用私人 D-Bus，不添加全局 D-Bus 策略。视频接收程序只统计帧和格式，不保存屏幕帧或音频。

目前没有正式 HDMI 显示通路，未换 PL Overlay。即使后续真实 RTP 接收通过，仍需另行验证 HDMI 输出与 EEG 多任务并存。

最终审计：正式网页 HTTP 200；网页、采集和 NetworkManager 的 PID 与重启次数未变；原 AP/DHCP 均 active；不存在加载中的 `gl-mirror-*` 临时单元；受保护文件校验一致。采集服务的历史 NRestarts=178 不等于本轮新增重启。回退测试在电脑和板端均为 2/2 通过。

## 用户确认失败后的只读核查

用户提供的截图为手机系统无线投屏搜索入口，未列出接收器。收到此反馈后没有开启第四轮无线独占测试，也未重置手机网络。

板端只读复查确认 wlan0 仍为原 AP，网页、采集、AP、DHCP 均 active；当前模块为 `/lib/modules/5.4.0-xilinx-v2020.2/kernel/drivers/net/wireless/8188eu/8188eu.ko`，版本 `v5.3.9_28540.20180627`，srcversion `E4D760A842C64B571479C92`。板端保存的 `rtl8188eu-linux-v5.4.tar.gz` 实际是内核 staging 驱动树，不能仅因文件名相近就认定它是当前厂商模块的可匹配源码；本轮未找到足以核实匹配的源码构建清单，未修改或编译驱动。

已确认：故障发生在设备发现/连接建立前；没有视频帧可用于传输或解码诊断。推断：当前 MiracleCast、wpa_supplicant、厂商驱动、手机协议组合的发现兼容性值得优先检查。未知：接收端管理帧是否在空中正确发送/被手机接收，以及手机是否过滤了接收器声明。缺少独立空中抓包或已知良好组合对照，不能确定某一端就是根因。

上游 issue #453 及通过 GitHub API 读取的评论包含相似的“Linux 发现 Huawei Mate 20，但手机搜不到接收器”现象；其设备、驱动与本项目不同，维护者未给出可直接复用的确定修复，关闭 issue 也不表示问题已解决。不采用其中强行主动 connect、反复盲试或需要手机 root 的建议。
[MiracleCast 相似问题](https://github.com/albfan/miraclecast/issues/453)

可评估替代路线：Z15、ESP32 加入手机热点，手机经用户授权的鸿蒙原生录屏发送端送视频码流至 Z15。华为 AVScreenCapture 官方开发指导说明码流可用于桌面共享/直播，并要求用户同意录屏；这只是开发能力依据，不是本机应用安装、持续采集、720p30、后台联网或 HDMI 输出已经通过。制作/安装手机发送端属于新的实施范围，应先确认用户选择和签名部署条件，不直接安装应用、不把网页等同于系统录屏发送端。
[华为 AVScreenCapture 开发指导](https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/avscreencapture-c-basic-process)

证据入口：`mirror_receiver_20261007/stage.json`、`dependency_manifest.json`、`build.log`、`gst-*.txt`、`attempt1-journal.log`、`attempt2-journal.log`、`attempt3-journal.log`、`wifid.log`、`sinkctl.log`、`restored.json`、`final_audit.json`。无线日志含设备标识，属于本地诊断记录，交接时应按需要脱敏。

## 最后一轮兼容性检索与替代路线审查

2026-10-07 用户要求再集中核查一次，并评估现成手机程序或浏览器发送视频。本次只读日志、上游源码和公开文档；没有第四次独占无线测试，没有下载执行新组件、安装 SDK、连接手机调试、改驱动、改网络或改 PL。

MiracleCast 当前源代码中的 WPS 主设备类型为 `1-0050F204-1`，配对方法默认 `pbc`，本项目上一轮已显式改为 `push_button`。没有找到针对本机 HarmonyOS 6.1 + 厂商 8188eu v5.3.9 + wpa_supplicant 2.9 的可验证补丁。不能把不同手机/驱动的 issue、改设备名称或主动连接当作确定修复。缺少空中管理帧和已知良好接收器对照，根因仍未定位到某一端。现有软件声明成功不等于空中发现正常；后续若重走此路线，应先补能区分驱动与手机过滤的证据，而非重复同样的搜索窗口。

### 网页能力边界

普通网页不能通过读取另一个来源的网页 DOM，抓取抖音 App 或其它标签页画面。系统屏幕共享需浏览器实现 `getDisplayMedia`，并满足可信 HTTPS、用户动作和明确授权。Mozilla 的兼容性数据将 Chrome Android、Firefox Android、Safari iOS 标为不支持；该表没有 Huawei HarmonyOS 浏览器项，不能直接据此判定用户手机一定不支持，也不能承诺切换到电脑版网站就能启用。现有 HTTP 局域网页不是可信 HTTPS，不能用其中没有 `navigator.mediaDevices` 一项来单独判定浏览器永久不支持。

本页自己加载的可访问视频元素与整个屏幕是不同对象；即使支持 `captureStream`，也不等于可以读取另一个来源的抖音页或受保护的视频。AirDroid Cast 的官方说明明确把手机 App 作为发送端，网页作为接收端；其纯浏览器发送说明针对桌面 Chrome/Edge。未找到其官方说明确认 HarmonyOS 6.1 原生发送端，不能用 Android APK 或“无需安装的网页接收端”替代这一验证。

### 现成鸿蒙 App

幕连官网列出 HarmonyOS 下载入口（华为应用市场 C101207863），并记录鸿蒙版 V1.0.0 于 2025-09-16 上线。这是一个比仅写“兼容鸿蒙”的旧 Android 教程更具体的候选；仍需在用户手机验证实际安装和共享能力。官网列出的运行系统为 Windows、Mac、Android、iOS、HarmonyOS，未列出 Z15 的 32 位 Linux 接收端。它不能直接作为“手机安装后，现有 MiracleCast 就能收到”的证据，也不把 Windows/Android TV 安装包部署到 ARM Linux。

### 调试连接实时投屏候选

HOScrcpy 上游提供鸿蒙设备视频流投屏 SDK 和网页示例。另一个开源调用项目 `ns-zzj/dsh-hos-scrcpy` 明确使用 HDC USB 或 TCP 连接，并在 Java 回调中将 H.264 送到本机 WebSocket；已读其桥接源代码和第三方声明。这可能绕开 Miracast 发现，但属于尚未验证的替代方案，不是现有故障修复。

其第三方声明指出关键 SDK 是预编译 JAR、包含按设备内核版本区分的签名设备端组件，且上游版权署名存在缺口。调用层公开不等于整个 SDK 可重建，也不能由此保证手机 6.1 兼容或 32 位 ARM 可用。HDC 官方说明推荐 64 位 Linux 主机；必须单独解决 Z15 ARMv7 主机工具适配，不能拿 x86_64/arm64 二进制当 armhf 使用。手机需要主动授权调试；某些路径首次需 USB 切换至 TCP，尚未确认本机能否全程无线。调试权限比只允许录屏更广，需要另行说明和授权，不开放到公网或无保护的局域网。未安装带 AI 控制的整套插件，也未启动任何手机命令。

这一路线没有以“开发自有 HAP 并注册开发者账号”为前提，但也不能承诺零配置、零安装或已可独立在 Z15 运行。先确认用户是否接受调试方式，再做隔离兼容测试；PC 可作为早期诊断工具，不能成为最终必须在线的转发节点。

### 视频内容投屏与下一项最小检查

若手机浏览器或视频 App 有 TV/投屏入口，且实际采用标准 DLNA/UPnP，可评估同 LAN 的 Linux 媒体接收端，先用普通可播放视频检查发现、媒体地址和解码。它传的是视频内容/播放地址，不是整个手机桌面；抖音分享链接也不等同于可直接播放的码流地址，不能预先承诺每次滑动短视频都同步。拒绝获取或上传登录 cookie，不绕过登录、DRM 或应用权限。尚未在本机建立 DLNA 视频接收或渲染链路。

已向用户询问手机浏览器名称及播放器是否有 TV/投屏按钮；无须先注册账号、安装 App 或改网络。即使这条接收路线通过，当前正式 PL 没有 HDMI 显示通路，仍须单独验证显示与 EEG 服务共存；接收码流不等于 ARZOPA 已显示。

核查来源：

- [MiracleCast 相似发现问题](https://github.com/albfan/miraclecast/issues/453)
- [屏幕共享 API 与使用约束](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia)
- [Mozilla 浏览器兼容性原始数据](https://github.com/mdn/browser-compat-data/blob/main/api/MediaDevices.json)
- [网页同源安全边界](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Same-origin_policy)
- [AirDroid Cast 官方流程](https://www.airdroid.com/guide/cast/)
- [幕连系统和鸿蒙版信息](https://letsview.cn/screen-mirroring)
- [HOScrcpy 上游](https://gitcode.com/OpenHarmonyToolkitsPlaza/HOScrcpy)
- [HDC/H.264 桥接候选](https://github.com/ns-zzj/dsh-hos-scrcpy)
- [候选的第三方组件声明](https://github.com/ns-zzj/dsh-hos-scrcpy/blob/main/THIRD_PARTY_NOTICES.md)
- [HDC 官方工具说明](https://github.com/openharmony/developtools_hdc/blob/master/README_zh.md)
- [华为官方对应用内内容投屏的说明](https://consumer.huawei.com/cn/support/content/zh-cn15790907/)
