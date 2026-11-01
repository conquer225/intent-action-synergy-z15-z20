# 手机热点网络切换（2026-10-06，已连接）

## 最新结论

Z15 已以 STA 模式加入 `QqqQ`。实际租约为 **`192.168.43.6/24`**，网关/DNS 均为 `192.168.43.1`。新地址的网页已通过同热点电脑访问（HTTP 200），板卡外网 HTTP 探测返回 204，出站路由明确使用 wlan0。用户此前看到的 `192.168.43.5` 未用作板卡身份判断；本次以 DHCP 租约及原 SSH 主机密钥确认了 `.6`。

手机入口：`http://192.168.43.6:9102/mobile`；主页面：`http://192.168.43.6:9102/`。手机热点宿主自身浏览器访问仍需用户确认。未连接/烧写 ESP32，未实现无线视频解码或 HDMI 投屏。

本次为运行时连接：原 AP 开机配置未改变，正常重启后仍使用原 `GuardianLoop-Z15`。现有网卡在 STA 模式时不同时提供原 AP。热点掉线超过约 90 秒时，临时 guard 会尝试恢复原 AP；不要将其表述为已完成全部故障注入验收。

最终报告：`eeg_apps_z15/output/gl-phone-3111b3b575/result.json`。正式版本清单的 48 个文件全部校验通过；保护文件哈希及 boot ID 未变化，成功切换前后网页 PID 677/采集 PID 2077、NRestarts 0/178 均一致。

## 范围与状态

用户已打开手机热点 `QqqQ`（2.4 GHz），尝试让 Z15 加入该网络。本次仅临时网络切换；未重新烧录 ARM/PL，未编辑模型、正式程序、启动镜像或已有 AP 服务文件。密码不记录在本文、源代码或结果报告。

电脑已成功连接手机热点：IPv4 `192.168.43.4`，手机网关 `192.168.43.1`，网关 ICMP 成功。电脑最后恢复原 `JLU.WIFI`。不能据此宣称三个设备已互通或已支持视频投屏。

## 切换前确认

- Z15：内核 `5.4.0-xilinx-v2020.2`，boot ID `e0fd1f19-9ccd-494d-b262-7a5924046336`。
- 无线驱动 `8188eu`，网卡 MAC `00:0f:00:40:81:09`，原 AP `GuardianLoop-Z15`，地址 `192.168.50.1/24`。
- 网线断开，Z15 `eth0` 为 DOWN，仍有 `192.168.2.99/24` 地址；电脑有线适配器也为 Disconnected。
- 正式网页 PID 677，采集 PID 938。采集 NRestarts 已为 177，切换前已有无完整 Cyton 数据日志，不能归因于此次网络测试。
- NetworkManager 1.22.10；wlan0 被已有配置标为 unmanaged。未编辑该配置。
- 未发现正在运行的眼动/HDMI会话。

## 实际尝试及恢复状态

控制脚本：`eeg_apps_z15/connect_phone_hotspot.py`，使用现有 SSH、wpa_supplicant、dhclient、systemd-run；没有安装驱动或依赖。

第一处 SFTP 写入模式错误已修正，此前未启动网络切换。

正式尝试目录 `/home/xilinx/gl-phone-f00b1831fe`：脚本、DHCP hook 和连接配置均在新建受限目录，配置保存派生 WPA PSK，没有覆盖原 AP 配置。安排了 6 分钟自动回退，再停止原 AP/DHCP 服务，尝试临时 STA 模式。新网络中未找到匹配 Z15 SSH 主机密钥的设备；探测噪声已停止，电脑恢复 `JLU.WIFI`。

等待回退期间原 AP 暂时无法连接。用户接回网线后，从 `192.168.2.99` 读取日志，确认定时回退执行成功，AP/DHCP 已恢复 active；没有重启或重新烧录。

第一次失败的日志为 WPA 4-Way Handshake failed / WRONG_KEY，没有 DHCP 租约。核查确认传入 Z15 的派生密钥与用户给出的口令一致，但电脑成功连接 QqqQ 所使用的保存口令与用户给出的口令不一致。重试使用该同一热点已验证可用的 Windows 配置，在内存中取出并派生 WPA PSK，只写入板端受限临时目录，不输出、提交或记录明文口令。此后关联及 DHCP 成功。

本地诊断记录：`eeg_apps_z15/output/gl-phone-f00b1831fe/result.json`。其中只有切换前哈希和状态、电脑地址，不是通过报告。

待核查的临时 unit 前缀 `gl-phone-f00b1831fe`，后缀为 `switch`、`wpa`、`dhcp`、`rollback`。不要停止其他 wpa_supplicant/NetworkManager 或其他人的服务。

## 成功连接后的临时对象及回退

- 新目录：`/home/xilinx/gl-phone-3111b3b575`（受限权限，含运行时连接所需的派生 PSK；不应作为公开交付包传播）。
- 临时 wpa、dhcp、guard unit 均 active；成功后停止 6 分钟未确认回退定时器。
- 这些 unit 没有永久安装/启用，不改 SD 启动镜像；重启会回到原 AP。
- 有线访问可用时，可执行 `sudo /usr/bin/python3 /home/xilinx/gl-phone-3111b3b575/network.py rollback` 恢复原 AP。该操作会中断当前无线访问，因此应从有线通道执行。
- CLI 的 `--wired --saved-profile --ssid QqqQ` 路径已实测通过。早先无线-only 子网发现仅属失败尝试，不应优先使用；后续应通过已有 DHCP 租约定向验证设备，避免全子网探测。
- 临时 unit 增加 5 秒停止超时，回退对非必要停止超时继续执行。未进行关闭手机热点的故障注入，也没有更改正式网页、模型或 PL。
