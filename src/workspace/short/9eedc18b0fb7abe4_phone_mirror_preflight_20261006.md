# 720p 手机整屏镜像接入前检查

日期：2026-10-06。目标是让 Huawei Pura 80 Pro（用户截图为 HarmonyOS
6.1）无线发送屏幕，Z15 接收后在 ARZOPA 显示，不以电脑作为最终运行依赖。
本轮只读检查，没有安装软件、修改网络角色、停启正式服务或加载 PL。
原始命令与结果见 `PHONE_MIRROR_PREFLIGHT_20261006.json`。

## 已确认

上轮 720p 原生 FFmpeg 解码＋BGR 转换台架约 34–39 fps，可据此选定
720p/30 为目标，但尚不是手机投屏、HDMI 或脑电正常预测负载的验收。
本轮没有把这个结果改写成可直接出画的完整播放器。

板卡现在已回到 `GuardianLoop-Z15` 热点，wlan0 为 AP、地址
`192.168.50.1`；有线 `192.168.2.99` 正常。上轮手机热点守护日志显示
`ORIGINAL_AP_RESTORED`，不是本轮主动切换。不能继续假定板卡仍在
`192.168.43.6` 或手机热点始终打开。

网卡 USB ID 为 `0bda:8179`，驱动 `8188eu`，只有一个无线物理设备。
`iw list` 报告 managed/AP/P2P-client/P2P-GO，但同时报告
`interface combinations are not supported`。因此 P2P 角色有初步条件，
但没有“手机热点 STA＋Miracast P2P 同时运行”的能力证据。仅有 P2P
模式名称也不能证明实际握手、收流或互联网并行可用。

板端没有找到 `miracle-wifid`、`miracle-sinkctl`、`gst-launch-1.0` 或
`ffmpeg` 命令。已有 FFmpeg 库可供自有 C 探针使用，不能因此说已有
Miracast 接收服务。

现有 GStreamer 运行库中，实际工厂查询结果：

- 已有 udpsrc、rtpjitterbuffer、rtpmp2tdepay、autovideosink、videoconvert、appsink。
- 缺少 tsdemux、h264parse、avdec_h264；Python 的 Gst introspection 也不可用。
- `/usr/bin/rygel` 存在，但未启动它，也没有据此认定整屏镜像可以工作。

构建工具 gcc/make/cmake/autotools 已有，libsystemd 开发头文件缺失，
pkg-config 也找不到 libsystemd、libudev 开发信息。普通
`apt-get -s install` 模拟显示当前包索引没有所需安装候选；没有运行
`apt update`、`apt install` 或修改软件源。

正式网页 PID 677、采集 PID 2077，仍 active，NRestarts 分别为 0 和
178，与上轮一致。8 项保护文件哈希与上轮开始前一致。没有切换显示
Overlay、主动访问 HDMI/VDMA 寄存器或停止脑电采集。

## 选定候选与明确不等同的功能

镜像接收优先评估 Miracast。华为官方说明将镜像投屏与特定应用的媒体
投送分开；通用排障文档说明 Miracast 用于音画镜像，DLNA 的说明限定
特定媒体应用及旧系统版本。因此现有 Rygel/DLNA 不是这台 HarmonyOS
6.1 手机刷抖音时整屏镜像的已验证替代方案。
[华为无线投屏说明](https://consumer.huawei.com/cn/support/content/zh-cn15871281/)

开源候选采用 MiracleCast 的接收端，暂不安装。它有嵌入式接收用途，
需要 P2P Wi-Fi、wpa_supplicant、systemd/glib，并通过 GStreamer 输出。
其上游接收启动示例接管网络管理；不能不加修改照抄到目前的热点上。
[MiracleCast 上游](https://github.com/albfan/miraclecast)

上游播放器检查要求 tsdemux、h264parse、avdec_h264 等插件，板上尚缺
这些组件。下一阶段应先验证设备发现和视频收到内存，再接自有低开销
解码/显示路径；上轮直接 FFmpeg 的速度不是未测试 GStreamer 接收链路
的性能保证。
[上游播放器依赖检查](https://github.com/albfan/miraclecast/blob/master/res/test-viewer.sh)

## 下一步及授权边界

需要先获授权，才能下载/编译第三方接收器、补充缺少的用户态依赖，
以及暂时让 wlan0 独占为投屏接收角色。优先隔离目录和有限时会话，
不升级内核、不替换网卡驱动、不做系统整体升级；若必须改系统库或
网络管理配置，应先明确变更清单，不以泛化授权绕过检查。

首次验证只做“手机能搜到 Z15 → 建立连接 → 收到有效视频”，不切 PL、
不启 HDMI。暂时独占无线网卡会使板卡的无线网页连接中断，有线控制
保持；测试需有板端超时回退，结束恢复原 AP。手机能否保持移动数据
刷视频，以及热点能否与投屏共存，均需实际验证，不能预先承诺。

收到视频后才安排 HDMI 输出。当前正式 GuardianLoop PL 没有显示 IP，
已有 eye_wifi 显示 Overlay 会换掉整套 PL，仍需独立明确授权与回退方案。
本轮不生成 bitstream、不烧录、不停止采集、不要求佩戴。

若这一网卡的 P2P 握手失败或热点并行确实不成立，再比较可支持并行的
第二无线网卡、外接 Miracast HDMI 接收器或鸿蒙原生同局域网发送端。
目前没有要求用户购买硬件，也没有承诺任意 Android APK 可在该手机运行。
