# 手机热点内的 Bilibili 视频投屏接收测试

## 本轮范围

用户已在哔哩哔哩找到 TV／投屏入口，并确认手机个人热点开启。
本轮沿用已授权的临时接收器和用户态依赖测试：Z15 加入手机热点，
只验证 DLNA 发现和接收。不是全屏镜像，不保证抖音可用，不输出 HDMI，
不加载 PL、不改开机镜像、不重启脑电服务，不保存视频画面。

## 已确认

- Z15 仍是 PYNQ Ubuntu 20.04、ARMv7/armhf、5.4.0-xilinx-v2020.2。
- Rygel 0.38.3 已在板上，但原插件目录仅有 External、MediaExport、MPRIS；
  原先没有 Playbin 接收插件，不能仅凭安装了 Rygel 就认定可接收视频。
- 补充 `rygel-playbin` 和 `librygel-renderer-gst-2.6-2`，均为 Ubuntu focal
  官方仓库的 armhf `0.38.3-1ubuntu1`。包大小及 SHA256 与仓库索引核对；
  本轮未独立验证 Release 的 GPG 签名。
- 仅解包至 `/home/xilinx/gl-dlna-20261007-2067bd11/sysroot`，没有 `apt install`，
  未改系统依赖。包源、依赖及校验值见 `dlna_receiver_20261007/dependency_manifest.json`。
- 复用隔离目录 `/home/xilinx/gl-mirror-20261007-000905` 中的解码依赖，
  `ldd` 没有缺库；`playbin`、`fakesink`、`avdec_h264`、`souphttpsrc`、
  `qtdemux` 五个 GStreamer factory 检查通过。
- Z15 成功加入 QqqQ，实际 DHCP 地址为 `192.168.43.6/24`，网关 `.1`。
  热点凭据只在权限受限的配置文件中使用，不记录在本报告。
- Rygel 在私有 D-Bus 会话运行，只加载 Playbin，关闭媒体分享、上传、删除、
  转码，音频和视频均接 `fakesink`。独立 HTTP 端口是 9119。
- 板端绑定 WLAN 地址的 SSDP 搜索收到 1 个本机描述符；HTTP XML 核查得到：
  `GuardianLoop-Video`、`MediaRenderer:2`，含 `AVTransport:2`、
  `RenderingControl:2`、`ConnectionManager:2`。
- WLAN 地址的正式网页 `:9102/` 返回 HTTP 200。
- 切换前后八个受保护文件 SHA256 完全一致；正式网页 PID 677、重启数 0，
  采集 PID 2077、历史重启数 178，均未变化，处于 active。
- 本地回退逻辑和配置检查 3/3 通过，Python 编译检查通过。

## 尚未确认

用户反馈“搜到，但连接失败”：手机发现接收器已确认，播放仍未通过。
当前没有真实手机视频解码、实测帧率、音画同步或 HDMI 显示结论。
若后续连接成功，需继续检查接收端实际状态，不能仅凭手机提示连接成功
就报告整条投屏通过。

## 已定位的连接兼容问题及隔离修正

原接收器收到手机的视频链接，记录了 HTTP 404 和 XML 实体解析错误。
对该次手机主动发送的同一 CDN 链接做限量诊断，未打印授权参数、未保存媒体：

- IPv4 HEAD / GET 均在 5 秒限时内未完成；不据此推断手机热点不能上网。
- IPv6 HEAD 返回 `404 application/xml`。
- IPv6 GET `Range: bytes=0-0` 返回 `206 video/mp4`。

因此确认了一个资源预检查差异，而非网卡带宽不足的证据。
[Rygel 0.38.3 原版 AVTransport 源码](https://raw.githubusercontent.com/GNOME/rygel/rygel-0.38.3/src/librygel-renderer/rygel-av-transport.vala)
会先 HEAD 查询；其 GET 回退条件不含 404，故该链接会被提前拒绝。
这不等于 XML 格式问题已关闭，也不等于发现了所有连接失败原因。

隔离 `head_compat.so` 只注入本轮 Rygel 私有进程：对已实际观察到的
`upos-sz-estgcos.bilivideo.com` 的 HEAD 改用一字节 GET。
HTTP 206 验证成功后仅为 Rygel 的预检查归一化为 200；404 不变。
若服务端忽略 Range 返回完整 200，立即中止，不整段下载。
正式系统没有全局 LD_PRELOAD、库替换或服务修改。

板端 gcc `-Wall -Wextra -Werror` 编译通过；本机 HTTP 测试验证请求顺序
`GET / GET / HEAD / GET`，结束状态 `200 / 404 / 404 / 7`：
成功范围读取可通过；错误保留；非匹配主机不改；不受限响应中止。
测试环境的 loopback 匹配开关不在实际接收器设置中。
编译和测试前两个尝试未通过，未注入接收器；只有上述通过版本被启用。

启用后仅重启本轮接收器；再次 SSDP/描述符核查通过，正式文件仍一致。
原独立网络恢复定时器不延长；已请用户进行一次补测。
尚未取得修正后的手机播放结果。

## 有界运行与恢复

网络切换前已设置独立的 12 分钟恢复定时器；接收器最长运行 600 秒。
网络保护进程仅管理本轮 transient 单元；最终恢复 GuardianLoop-Z15 AP 和 DHCP。
定时恢复尚未在本轮到点，因此当前不声称本轮实际回退已验证。

本地控制入口：

```powershell
& 'D:\Users\lenovo\anaconda3\python.exe' dlna_receiver_20261007\run_test.py status
& 'D:\Users\lenovo\anaconda3\python.exe' dlna_receiver_20261007\run_test.py stop
```

`stop` 只关闭本轮接收器并恢复原 AP；不会卸载或改写正式 PL。
重复恢复在原 AP 已健康时不会再次清空 WLAN 地址。端口状态和日志输出会
遮蔽 HTTP URL，避免把媒体授权链接写入对话。

配置依据：板上 `/etc/rygel.conf` 的 Playbin 配置注释，以及
[Rygel 官方配置文档](https://gnome.pages.gitlab.gnome.org/rygel/configuration.html)；
新版文档与板上 0.38.3 有差异，实际运行和服务 XML 才是本轮就绪证据。

## 第二次反馈与后续有界测试

用户补测反馈“一直显示正在连接中”。日志确认 17:38:48 UTC 请求到达并
出现 XML 实体解析错误，17:38:56 原定时器关闭接收器。此前 HEAD 兼容
计数为 0，故不能声称手机补测已进入媒体读取，更不能声称问题已解决。

恢复脚本的首次快照记录 `ap_restored=false`，随后只读检查确认 AP、DHCP
均 active，地址 `192.168.50.1/24`，类型 AP、SSID GuardianLoop-Z15。
这是恢复就绪检查过早，已补 15 秒内有界等待；再次执行恢复验证为 true。
本地增加延迟启动回归测试，不会反复清空已经健康的 AP。

隔离兼容库增加有界 SOAP/DIDL 文本转义：仅在 AVTransport 的 SetURI 文档
或 DIDL 资源文档中转义裸 `&`；有效实体保留，CDATA、DOCTYPE、超出 64 KiB
及其他文档不修改。8 个样例验证了参数完整性及不放松 XML 结构。
这只是修正候选；手机实际请求是否因此通过仍需本轮日志证明。
依据是 [GUPnP 控制处理源码](https://raw.githubusercontent.com/GNOME/gupnp/gupnp-1.2.3/libgupnp/gupnp-service.c)
的 XML 内存解析入口；未替换系统 XML 库。

增加私有 fakesink 的原始视频帧计数，仅输出数量和分辨率，每 5 秒最多
一条状态；不读取或保存像素。GStreamer 三帧合成测试验证帧总数为 3、
128×72、正常 EOS；这不是手机视频的帧率证明。测试曾暴露接口符号及
模块作用域问题，未通过版本未用于手机成功结论；最终显式解析已加载的
GStreamer 库，实际 Rygel 启动和 SOAP 状态查询通过。

复用隔离目录开启新 transient 前缀 `gl-dlna-20261007-2067bd11-r810bc3`，
启动中有一次进程退出 133，修正作用域后 17:54:30 UTC 重新启动成功。
17:54:43 查询 `NO_MEDIA_PRESENT / OK`、位置 0，说明接收器可响应控制且
当前尚无手机视频。受保护文件、正式网页和采集仍与测试前一致。
独立恢复定时器预计 18:01:47 UTC 到点；已请用户取消旧连接后重新发现。
截至这份记录，手机实际播放结果仍未确认，HDMI 未操作。

## 手机进入控制页后的核查

用户截图已显示 GuardianLoop-Video 控制页和“换设备”按钮，但进度
`00:00/00:00`。该按钮不表示需要购买或替换硬件。板端对应结果为
`STOPPED / OK`，Track 1，时长与位置均零；无实际解码帧。
本轮 DIDL 转义计数为 1、XML 实体错误为零，说明该请求已跨过前一项
解析报错，仍不能把手机控制页当作视频播放成功。

本轮实际媒体主机变成 `upos-sz-mirrorbd.bilivideo.com`，日志明确报告
域名解析临时失败；没有进入前一媒体主机的 HEAD 兼容分支。
18:01:47 UTC 独立定时器到点，实查 AP/DHCP 恢复、地址回到
192.168.50.1，restore.json 为 true。正式 8 文件、网页和采集进程状态
仍与测试前一致。新增本地恢复回归测试共 4 项通过。

继续请求下复用隔离依赖，新前缀 `gl-dlna-20261007-2067bd11-r8f80a8`，
恢复定时器为板端 18:14:59 UTC。新接收器响应 NO_MEDIA_PRESENT / OK。
运行时设置 core 大小为零，只作用于接收器子进程；没有保存视频像素。

DNS 对照只查询这一个实际媒体域名，不改系统配置：本地 stub
127.0.0.53 的 A 查询超时、AAAA 正常；直接向手机 DNS 192.168.43.1
查询 A / AAAA 均成功；直接向 223.5.5.5 查询也成功。这将问题范围收窄到
板端 resolved 与当前热点 DNS 的组合，尚未证明是其中哪一端的协议问题。
依据 [systemd 的逐链路 DNS 接口说明](https://www.freedesktop.org/software/systemd/man/247/org.freedesktop.resolve1.html)，
本轮仅把 wlan0 的运行时 DNS 改为 223.5.5.5；没有改 resolv.conf 或服务
配置。现有 rollback 的 `resolvectl revert wlan0` 会移除该临时设置。
修改后 resolved 的 A / AAAA 查询和 getent 全部正常；原用户投屏链接的
IPv4、IPv6 单字节 GET 均返回 206 video/mp4、Content-Length 1。
这验证该链接可以访问，不证明实际解码或 HDMI 输出。

新增 inspect_trial.py 只输出媒体主机和脱敏报错；probe_media_headers.py
只读取 HEAD / 一字节 GET、不打印媒体授权参数；probe_dns.py 不改 DNS
配置。手机已被请求取消旧投屏后重连，实际播放和输出仍待确认。

## 终止投屏尝试，转向本地文件方案

用户再次反馈 `00:00/00:00`，提出手机分批上传视频、Z15 本地播放。
末轮日志有 5 次 DIDL 修复、零解码帧报告；接收器达到预定运行上限
而退出，Result=timeout。没有据此宣布手机视频播放成功，也没有继续
扩展投屏兼容补丁。手动结束本轮并取消其恢复定时器；实查原 AP/DHCP
均 active、wlan0 回到 192.168.50.1，本轮 DNS 设置已撤销。
8 项受保护文件未变化，正式采集和网页状态保持。

新的只读核查：根分区 29G，约 17G 可用；/boot 仅约 107M 可用。
视频文件应存根分区的独立媒体目录，不能把 /boot 当作视频仓库。
root + XILINX_XRT=/usr 的 PYNQ 登记仍为正式 guardianloop_pynq.bit，
IP 列表是 PS7、AXI DMA、GuardianLoop registers/quality/DE/HGB，
没有显示 IP。普通用户未设置 XRT 的查询失败，未据此认定 PL 为空。

已有 /home/xilinx/tobii_z15/media/playlist.json 包含两个视频素材目录：
175 帧和 102 帧，均 10fps。已读取的 media_players.py 使用
frame_000001.jpg 起的 640×360 图片序列，不是通用 MP4 播放器。
hdmi_guide.py 的显示路径加载 eye_wifi.bit，并通过自有 VDMA 接口输出；
本轮没有运行该入口或替换正式 PL。

文件上传不依赖 Miracast/DLNA：手机在同一局域网的网页选择本地文件，
由 Z15 保存、校验，再发布新播放列表；新批次完整前保留原批次。
该思路可行，但本轮仅完成可行性和现状核查，未部署上传服务、MP4
播放器、定时任务或显示共存工程。建议先前台手动上传一个有效 MP4
完成端到端验证，再扩展到批次与板端定时切换。
后台网页计时不能视为可靠的三小时无人值守上传承诺，参见
[MDN 后台页面计时策略](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API)。
