# 手机短指令入口及眼控恢复状态（2026-10-14）

最新进展：用户再次重新供电后，眼控已恢复正常 0124；有限 hello 与约 15 秒现有定位程序收包通过。已补齐 UVC 绑定后的保持唤醒规则并纳入 88 项启动 pin；未刷固件，未重新标定。当前 Cyton 本体关闭、HDMI 静态主页、实体输出禁用。后文保留各轮历史，详细新证据见末节；未证明所有异常重启根因或下一次实际冷启动已经解决。

## 用户要求与当前边界

用户要求补齐手机前进／后退／左转／右转／停止并恢复眼控。当前 ESP32 已运行禁用 GPIO 的台架固件，原厂动作网页不再是运行固件。用户提到手机停止作为停止手段，本轮未取得独立物理停止手段、GPIO 接线和实体停车验收，因此没有改 ESP32 固件、解锁电机或进行真实车轮动作。

已补齐并上线的是**手机短指令入口、认证 API、既有台架协议发送及明确回执**，不是实体遥控／载人运行已完成。

## 软件实现

- 原手机综合页增加前进、后退、左转、右转、停止、切回 SSVEP 六个按钮。
- 使用现有私有访问码和同源校验，只允许固定方向值，不接受任意目标地址、路径或脚本。
- Web 将最新手动意图写入 RAM；原轮椅发送进程仍是唯一 ESP32 命令所有者，手动操作不经虚假 EEG 输入。
- 手动意图有效期 250 ms，接收端已有 300 ms 租约、不持续续发。这里不是实体运动／停车时长的测量或保证。
- 停止后保持手动停止，显式“切回 SSVEP 接口”才解除手动仲裁；严重疲劳和未确认的人工强停仍优先。
- 旧 boot、过期、无效和离线期间的方向请求不重放；不会自动发出 ESP32 本机 ARM，不将仅显示闪烁或历史 EEG 当作电机指令。
- 显示仍明确标注 GPIO 禁用、未确认车轮状态。切到已启用 GPIO 的其他固件会被现有 BenchReceiver 身份合同拒绝；实体控制需另行验收与接入，而不是隐式放行。
- 手机／服务新增正常运行眼控 `0124`、维护接口 `0102`、缺失设备的区分。维护／缺失时阻止启动无效采样／标定，保留原模型与原生程序。

复用 `bench_network_bridge.BenchReceiver`、RAM 原子写入和网页恢复入口；未另写采集器／USB 驱动，遵循 code-humanizer Guard。

## 软件验证与部署

Windows 新服务器 19 项、轮椅链路 16 项测试通过；JS 测试通过。Z15 隔离运行服务器、手动／SSVEP 链路、既有网络协议共 53 项通过。第一次隔离执行遗漏既有眼控 `selection` 的源路径，修正测试 PYTHONPATH 后通过，未为此修改生产选择逻辑。

备份和计划目录：`/home/xilinx/gl-phone-manual-20261014-sfZOf2`。安装目标仅 5 项：原 `media_server.py`、`wheelchair_link.py`、手机 HTML／JS、`boot-pins.json`。原文件备份位于其 `backup` 子目录。

安装只重启网页／发送服务，未重启 HDMI、采集或重载 PL。安装和验收 boot=`9647dc2b-638c-4aad-9e68-0dd9ca58bd2a`；HDMI `play-b00588d7` PID 814、采集 PID 773 前后不变，87 项 pin 完全一致。

实际 API 验收前先 GET ESP32 状态，核对未许可、GPIO 禁用。随后前进意图得到 `local_permit_required`、direction=stop、sent=false；没有发送方向票据／实际运动。停止意图得到 `manual_stop`、direction=stop、sent=true；这仅证明停止协议回执，不是车轮制动反馈。原主页静态，四角停止、物理输出 false，最终手动停止模式保持。

本地证据：`D:/ican/codex_project/phone_video_upload/output/mobile_manual_20261014` 的 `stage.json`、`board-tests.json`、`installation.json`、`acceptance.json`。

## 眼控：仍未恢复，不能称为完成

最初 boot `6fbf1da8-76b6-404e-afa4-a608924d609e` 没有 EyeChip。用户按要求重插后，现场 boot 变为 `13df5dad-edf2-4a77-a4f0-246c649c1da9`，眼控同一序列号 `CN033F74DTOB186P0822A00` 在 `1-1.4` 枚举为 `2104:0102`。这是不同于正常采样 `2104:0124` 的实际接口，不是坐姿、标定精度或遗漏另一份 PL 的证据。

限时只读 GETSTATUS 返回 10 字节，bStatus=37、state=10、written=0。核对同设备身份和零写入后，仅发一次 CLRSTATUS，返回 0；读回 bStatus=0、state=2、written=0，PID 仍为 0102。未 ABORT、DNLOAD、提交固件、USBDEVFS_RESET、模式切换或整板复位。清除错误标志**不等于恢复采样**。

核对协议参考 [Tobii ET5 维护工具源码](https://github.com/Aetherall/tobiifree/blob/main/assets/flash_firmware.c)。该工具的正常 PID 为 0313，本工程为 0124，不是相同型号；只参考已由现场响应核对过的状态查询／错误清除字段，没有使用其中签名头或固件。不能拿 ET5 blob 恢复此 OEM 模组。

用户再次仅将眼控 USB 断电约 30 秒并插回后，电脑 SSH 和手机页均曾不可用；随后网络恢复，boot 变为 `9647dc2b-638c-4aad-9e68-0dd9ca58bd2a`，HDMI 自动恢复主页，眼控仍 0102。可以确认期间发生了整板重启，不能仅说是网页断线；尚未确认是用户额外重新供电、供电／接触、USB Host／内核或设备导致的唯一原因。不能仅凭插接与重启时间相邻就宣布根因。

查阅本工程源码／现有快照和电脑已安装 Tobii 目录，未找到已核对匹配此 OEM 模组的恢复固件。ProgramData 中找到的 RGB 神经网络 `.bin` 是模型资产，不作为设备固件。没有新增或调用第三方恢复固件，也没有要求把眼控接电脑反复验证。

眼控恢复当前需要用户提供确切模组型号／原配恢复驱动或厂家提供的对应固件与恢复步骤；本轮到此停止猜测性 USB 模式写入和重复标定。

现场证据另在 `D:/ican/codex_project/phone_video_upload/output/shoot_ready_20261014`：`manual-controls-eye-replug.json`、`manual-controls-eye-device-status.json`、`manual-controls-eye-error-clear.json`。新固件完整性、实体电机遥控、真实眼控采样和更新后的再次冷启动，均不能作为本轮已验收项目。

## 用户要求复用历史成功步骤，并提供模组照片

照片标签为 `CN-033F74-DTOB`、`1-86P-0822-A00`，组合后与板端序列号 `CN033F74DTOB186P0822A00` 一致；部件号 033F74 可作为 OEM 资料检索线索。第二张 PCB 丝印没有提供可直接核对的恢复固件版本，不用它替代 USB 身份和匹配检查。

再次完整核对历史成功证据：

- `eye-port-crossover-hello.json`：boot e388785e，在用户把眼控移到原接收器口后，同一模组已枚举 0124；既有有限 hello-only 程序返回 OPEN_CONTROL=0、79 字节发送／43 字节接收、status=0。没有 DFU 写入或 PL 重载。
- `repower-eye-replug-audit.json` 和 `repower-eye-hello-positioning.json`：用户重新给 Z15 供电并重插眼控后，boot aa3c4a18，设备已为 0124，再用相同握手工具与原 eye_start，实际收到约 41–47 cm 定位数据。后续三点及中／左／右快速检查完成记录见 `USB_COLD_BOOT_CHECK_20261014.md`。
- 清错／ABORT、退出维护模式、USB reset 超时的旧记录均不能当作恢复成功步骤。尚无已确认“某条软件命令把 0102 直接恢复为 0124”的成功记录。

本轮新的只读现场审计 `eye-history-recovery-current-audit.json` 确认：boot 仍为 9647dc2b，眼控在成功过的 1-1.4 端口，但 PID 0102；接收器 1-1.2。既有 hello-only 程序仍存在，SHA-256 `8afcdd8097045769d6407f81694cb9380b63fc4df0fad3b81a7bf13315a44fbd`。它的源文件不在原私有目录，不因文件名相似就擅自将其用于维护接口，也未改 PID 或端点。

官方资料新增候选：[Dell EyeChip Core Driver H1MVT](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=h1mvt) 明确适用 Alienware 17 R4／Windows 10。仅查询资料，没有下载、安装或从中提取／烧写固件；候选主机驱动适用列表不等于单独这块模组的恢复固件匹配已验证。

可复用的下一步是一次有明确关机和重新接入边界的冷启动恢复，再核对是否回到 0124，然后原握手／定位／三点流程。该方法曾在历史现场成功，但没有证据保证每次成功；本轮尚未执行新的 Z15 关机／复位／断电动作，需要明确告知并取得对应操作授权，不能把用户要求查旧方法扩大成任意固件或 USB Host 写入。

## 获用户明确许可后的安全关机准备

用户对上述一次安全关机／冷启动流程明确回复“允许”。执行前再次核对 boot=`9647dc2b-638c-4aad-9e68-0dd9ca58bd2a`、显示 `play-b00588d7`、当前 `eye_wifi.bit` 与正式恢复 bit 的预期摘要；87 项 pin、正式发布 57 项文件均一致，眼控无活动会话、物理输出 false。

只调用已有 `hdmi_live_session.py restore`。独立关闭 unit 正常退出，原显示报告确认 original_restored=true、buffers_released=true，PYNQ 当前 PL 实际为 `/home/xilinx/jupyter_notebooks/guardianloop_pynq/guardianloop_pynq.bit`。没有改 bit 文件、模型、手机新功能、SD 镜像或硬件接线。

随后停止采集／脑电网页／HDMI 开机入口，并核对原显示、综合网页、watch 的 MainPID 也均为 0、inactive。AP、DHCP、采集、网页、HDMI 入口的开机设置仍 enabled；启动 pin 再次通过，磁盘 os.sync 已返回并同步了准备报告。

最后提交 5 秒延迟的 systemctl poweroff，得到 systemd-run timer／service 接受回执。这里确认的是恢复、进程停止、磁盘同步和关机请求接受；没有串口证据确认内核最终 halt，不把网络连接消失等同于全部硬件已断电。下一步需用户实际断电等待、眼控暂不插回，先启动 Z15 到静态主页后再插回眼控。

本地证据 `D:/ican/codex_project/phone_video_upload/output/eye_cold_recovery_20261014`：`shutdown-preflight.json`、`close-result.json`、`ready-to-poweroff.json`、`poweroff-request.json`。板端对应私有目录 `/home/xilinx/gl-eye-cold-recovery-20261014-AfHlhG`。

## 用户完成断电后报告主页恢复：插眼控前的边界确认

只读核对新 boot=`abe87956-f6fa-4ce8-9066-67bf2832aeac`，不同于关机前 9647dc2b；观察 uptime 约 139 秒。AP／DHCP／正式采集／脑电网页／综合网页／HDMI 入口均已自启动、NRestarts=0，87 项启动 pin 无差异，media 配置的 boot 身份已更新。

新的静态 HDMI 会话 `play-71bee202` 为 home/menu、RuntimeWatch 无错误，眼控会话为空、四角 inactive、物理输出 false。USB 仅见 Hub、网卡及接收器 1-1.2，没有 EyeChip，手机 API 对应 eye_device=missing；这与用户按步骤暂不插眼控相符，旧维护节点没有被沿用。

ESP32 仍在线并处于台架 STOP，手机功能文件在 pin 校验范围内保留。采集进程已运行，但日志仍为配置回复等待，不能将启动正常写作已收到有效 EEG。本轮不重启采集、不发 Cyton 初始化、不调整质量，也不启动眼控／闪烁／轮椅。

下一项仅请用户将眼控插回原 USB Host，再读取新设备枚举及身份。没有在设备尚未接入时启动无效标定；`0124` 恢复与真实握手／眼位仍待接入后验收。证据 `after-cold-start-pre-eye.json`。

## 仅插回眼控后出现整板重启：本轮冷启动未恢复眼控

用户报告眼控已插回，随后 HDMI 曾黑屏，再自动回到主页，并明确确认只插了眼控 USB，没有碰电源插头或复位键。在此期间，管理端尚未运行眼控 hello／eye_start，没有发送 USB reset、维护模式写入或 PL 下载命令。

只读核对 boot 从插眼控前的 `abe87956-f6fa-4ce8-9066-67bf2832aeac` 变为 `4c5f8dda-fab5-4258-8c7b-a06d92afcb49`，因此不是仅网页或显示服务重启。新 boot 的眼控 `1-1.4` 仍为 `2104:0102`，序列号不变；正常采样 `0124` 没有恢复。最后观察 uptime 555.80 秒、HDMI `play-aa121d6a` home/menu、eye 会话为空、四角 inactive、物理输出 false。

针对**确切的插入前 boot ID**查询 journal，而不是把 `journalctl -b -1` 的旧历史尾部当作本次事件：插入前 boot 的最后已记录消息在 uptime 223.10 秒附近，没有正常 shutdown／poweroff 流程、USB 插入事件或 panic 栈。wtmp 将上一登录标为 crash；新 boot 的 EXT4 日志有 recovery complete。这些支持异常中断，但没有留下足以唯一判断供电、USB Host／内核或设备故障的日志。此前启动的 FAT 未正常卸载警告本身不能确定本次重启原因，也未对已挂载分区运行 fsck 或改 SD 卡。

当前 systemd `RuntimeWatchdogUSec=0`，watchdog.service inactive，无进程持有 `/dev/watchdog*`；内核启动时打印 watchdog 驱动初始化不等于确认看门狗触发。该观测也不能完全排除上一启动中的所有硬件复位来源。`/sys/fs/pstore` 本机不存在，不能将“无持久崩溃日志”写成“没有内核崩溃”。用户自定义 EyeChip udev 规则仅针对正常 `0124` 设置 power/control=on，没有复位／关机脚本；本次没有修改该规则。

结论：本轮复用历史冷启动法**没有成功**，目前确认的是仅插眼控时段出现整板异常重启、重启后模组处于维护接口，尚未确认唯一根因。不再无条件重复重插／重启，也不改 PID／端点冒充运行接口。后续需不同条件的 USB 供电／Host 隔离对照，或经匹配验证的 OEM 恢复步骤；应先确认现有硬件和操作授权，再执行。

本地只读证据位于 `phone_video_upload/output/eye_cold_recovery_20261014`：`after-eye-insert-audit.json`、`reboot-diagnosis.json`、`pre-eye-boot-evidence.json`、`final-static-state.json`。完整历史 journal inventory 的首次查询超时；后续明确 boot ID 的查询成功。没有因此删除日志、禁用看门狗或改生产代码。

## 官方包离线核对：找到与正常 USB ID 一致的候选，不等于恢复完成

用户没有独立供电 USB Hub，授权只下载、解包和核对 Dell 官方 EyeChip 候选包。网络最初存在域名解析、连接中断；使用已存在的本地代理和 Dell 官方 downloads.dell.com 镜像续传，未改网卡、DNS、路由或代理配置。下载时仍校验证书；Windows 的撤销检查离线时仅使用单次 curl 的 revoke-best-effort 选项，没有关闭证书链验证。

- [H1MVT 官方页面](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=h1mvt)：完整包 141,185,584 字节，SHA256 `c26a69ad57129909b0bbc46b0b77eb191afa07cd48c5c54177656ae6afb95cf3` 与官网一致。IS4_base_DAW 候选平台 IS4BASEDAW、版本 1.1.9-5cebfcf，但其中 usb.merge 配置 PID=010A，并非现场历史正常的 0124。本轮不使用此旧候选；不能仅凭 Dell／IS4 名称推断直接适配，也没有据此宣称它在硬件层绝对不兼容。
- [HPMJF 官方页面](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=hpmjf)：完整包 176,583,960 字节，SHA256 `2b4e60ea5a10b830520f9e3253d1b3c7a3c1f224fa84603b85c6f3ab04c96ad8` 与官网一致。发布版 2.13.1.7294 A06，官网列表为 Alienware 17 R4／Windows 10；该主机列表不是当前 Lenovo／Windows 环境完整安装兼容性证明。

只使用电脑已有 NVIDIA 目录中的 7-Zip 22.01 解包；没有运行包内 EXE 或 msiexec。按 Burn XML 中的 SHA1 核对附加 CAB 与所取 MSI payload，再用 Windows msilib 的 MSIDBOPEN_READONLY 读取 TETFWFiles 的 File 表，恢复柜内 fil... 文件的真实名称。共 27 个固件候选。包内配置的 XOR 文本仅离线读取，保留源文件偏移；该静态读法不是固件签名验证器或可用于上传的格式实现，未把初期结构偏移猜测用于设备操作。

发现明确的同 VID/PID 候选：

- MSI 文件 ID `fil3D6B69279954C0AF38D9792B5EB2595D`，原文件名 `is4basedawmlk_firmware_2.27.0-4014648.tobiipkg`。
- 974,113 字节，SHA256 `4d3932bda76f6dcbf679628cd46c4e1aef3d883ffa8729c1db4158a7bcc2c50f`。
- 平台 `IS4BASEDAWMLK`，product/model=247、name=IS4_Base_DAW_MLK。
- 原包 usb.merge 内容 `/usb/VID = 0x2104`、`/usb/PID = 0x0124`；version.merge 为 2.27.0-4014648。
- 候选副本位于 `phone_video_upload/output/oem_eyechip_package_20261014/matching-candidate`，没有传到 Z15 或写入设备。

同包包含 `tobii_firmware_upgrade.dll`、`platmod_is4.dll`，PE 为 x86 Windows（0x14c），不是 ARM Linux 恢复程序。静态字符串可见 get_eye_tracker_metadata、get_package_metadata、PACKAGE_DEVICE_MISMATCH、DOWNGRADE_NOT_SUPPORTED 等检查入口；没有取得并验证这些 C ABI 的完整类型定义，不能猜 ctypes 参数调用，也没有因函数名似乎只读就未经核对执行。厂商组件仍需实际读取设备 `/hw/platformtype` 并判定匹配；配置为同 VID/PID 尚不足以证明这块具体设备可以安全写入此版本。未用 ET5 的签名头、flash_firmware 或 factory_reset 进行恢复。

离线核对期间 Z15 boot 仍为 4c5f8dda、主页正常，87 项 pin 无差异，EyeChip 0102。有限 GETSTATUS 成功返回 status=37、state=10、written=0；未发送任何 control OUT／USB reset／固件上传。官方材料找到并不代表眼控已能采样，也不解决此前插入时整板异常中断的唯一根因。

用户随后明确允许临时接电脑，用官方组件核对硬件平台，但**不写固件、不卸载现有 Tobii、不改 Z15**。电脑预检尚无 VID_2104 EyeChip；现有服务 Tobii Service（EyeX）、TobiiALENOVOYXX0、TobiiRGB 均运行。为避免自动升级／争用，尝试临时停止准确核对过路径的 Tobii Service；操作被本机会话权限拒绝，服务仍运行，Auto 开机设置未变，另外两项 RGB 服务未动。需用户手动停止该 EyeX 服务后再进行临时插入；不把“允许核对”扩展成安装整个旧驱动包、强写固件或自动运行更新器。

证据目录 `phone_video_upload/output/oem_eyechip_package_20261014`：`h1mvt-review-result.json`、`hpmjf-review-result.json`、`hpmjf-identity-mapping.json`、`official-recovery-components.json`、`windows-platform-preflight.json`；另有 `eye_cold_recovery_20261014/package-review-board-state.json` 与 `no-hub-readonly-status.json`。

## 用户再次供电且 Cyton 关闭：远程恢复运行接口和补齐唤醒时序

用户说明本人不在设备旁，Z15 已重新供电、Cyton 本体已关闭。只读审计看到新 boot `4164df6a-c01d-491c-82ed-a26f8b69e51d`，同序列号 EyeChip 在 1-1.4／设备 5 已恢复 2104:0124；FTDI 与 Wi-Fi 也正常枚举。主页会话 `play-8a947af9` 已自启，原 87 项 pin 无差异。最初启动阶段 API 的 player 为 null，后续已稳定为 home/menu；诊断读取没有把暂未创建的 player 当作工作中的显示。

眼控最初 power/control=auto、runtime_status=suspended。严格核对 boot、VID/PID、序列号、设备号、既有有限探针 SHA256 和无活动眼控／刺激／实体控制后，只将这一眼控 power/control 改为 on。原 hello-only 程序返回 OPEN_CONTROL=0、79 字节发送、43 字节接收、status=0、HELLO_ANSWERED=yes、退出 0；设备和整板 boot 未改变。没有运行固件恢复、USB reset 或重新加载 PL，暂不再要求用户临时接电脑。

原唤醒 udev 规则仅覆盖 USB device 的 add。现场 UVC 接口 1-1.4:1.1／1.2 已绑定 uvcvideo。对应 [Xilinx 2020.2 内核 UVC 源码](https://raw.githubusercontent.com/Xilinx/linux-xlnx/xilinx-v2020.2/drivers/media/usb/uvc/uvc_driver.c) 在成功 probe 后启用 autosuspend；结合开机之后又为 auto 的现场观测，这是原 add 规则不能覆盖晚到的 UVC 绑定的具体时序风险。此次未通过真实驱动解绑／重绑复现覆盖，因此不能把它宣布为此前整板异常重启或 0102 的唯一根因。

遵循 code-humanizer 的当前变更约束，只修改现有 `phone_video_upload/70-guardianloop-eyechip-power.rules`：add 分支收窄到正常运行 PID 和精确序列号；新增同一设备 UVC interface bind 分支，通过已验证存在的父级 ../power/control 保持唤醒。不新增守护服务、轮询器、通用设备恢复模块或内核补丁，不改维护接口／Cyton／网卡的电源策略。

安装备份目录 `/home/xilinx/gl-eye-power-rule-20261014-jIiZjV`，backup 内保留原规则和原 boot-pins.json。复用既有 install_calibration_repair 的 replace／sha／write_json，只安装规则、reload-rules，并把规则 SHA 加入原启动 pin。规则旧 SHA256 `33c1093b89edc1e3f1358b0dc31219fb53357f8fe3915b6937a3a9514aaf3549`，新值 `d7a0f71f3cd2293cd7fff1f243b394a259ef8f3b6c0a2715962756affedf3d66`；pin 数 87→88，其他 hash 不变，无 HDMI／采集／网页重启或 USB Host 复位。回退仅恢复这两份已核对备份、重新加载规则，并按需把这块眼控的当前 power/control 恢复 auto。

验证为真实 udev 规则引擎模拟：add 正常眼控、bind UVC 接口均匹配，bind 未绑定 UVC 的 vendor 接口不匹配。为避免“当前本来就是 on”无法证明规则命中，临时测试副本加 ENV 匹配标记；测试结束已还原无标记的生产候选，标记未留在正式规则。UVC bind 无属性写入错误。device add 测试出现 Invalid inotify descriptor，其原始无标记测试已有相同提示；不将其隐藏成所有 udev 诊断零警告。尚未另做实际冷启动或拔插验收。

最后调用现有 eye_start 一次，约 15.10 秒只停在 positioning，不调用确认位置／标定。7 次观察 connected=true、error=null，last_packet_monotonic 从 844.658 增至 857.048。用户不在屏幕前，双眼检测／瞳孔可用为 0%，valid=false、calibrated=false、control_enabled=false；这证明定位程序持续收到状态包，不是实际有效注视或准确性验收。随后 eye_stop、home 已应用；最终 eye={}、home、同一显示 session／boot、眼控保持 on、四角 inactive、物理输出 false。Cyton 本体关闭期间未采集或声称有效实时脑电，也没有开始真实联控。

现场证据：`eye_cold_recovery_20261014/after-user-repower-cyton-off.json`、`repower-runtime-hello.json`、`uvc-policy-order-audit.json`、`power-rule-marker-tests.json`、`power-rule-installation.json`、`repower-positioning-soak.json`。
