# SSVEP → 轮椅：隔离联调包

2026-10-15 最新：已部署 **手机持续遥控** 接收端 `guardianloop-wheelchair-remote-0.1.0`，GPIO 已启用，点击方向后持续执行，前台心跳失联/STOP 撤销且不自动恢复；不需逐次串口 ARM。正常页面 15 秒持续请求和异常撤销的断动力回归已通过，真实驾驶未验收。复用既有控制核，不改脑电模型、校准或 PL。详细证据和恢复路径见 [持续遥控记录](../docs/WHEELCHAIR_REMOTE_CONTROL_20261015.md)。下文 2026-10-06 是历史禁用 GPIO 台架基线，并非现状。

日期：2026-10-06。当前状态：**ESP32 已加入 Z15 热点，Z15 直发虚拟四方向＋停止联调通过；电机 GPIO 禁用，未接通实体脑控。** 当前部署记录见 `output/station_bench_deployment_20261006.json`，直接联网原始结果见 `output/direct_network_acceptance_20261006_02.json`，工程说明见 `firmware/README.md`。

当前 Station 台架应用为 901,616 字节，SHA-256 `291640902e3a9ccae22414b3dc56ce7f76f5b39105d0f4b5ffa51f0f692d20dc`。只写原 factory 分区 `0x10000`，工具写后摘要核验通过；没有写 bootloader、分区表或显式写 NVS。最终状态为联网／STOP／未许可／`motor_gpio_enabled=false`。八个合成网络用例通过：8/10/12/14 Hz 对应前进/后退/左转/右转，另有显式停止、无数据、坏质量、过期输入。四方向票据＋指令往返观察为 63–71 ms，停止续发后在 0.45 秒检查点均已撤销许可。**这是通信与虚拟状态检查，不是脑电准确率、实体停车时间或载人安全验收；电机动力必须继续隔离。**

ESP32 当前地址观察为 `192.168.50.72`（DHCP，可能变化），Z15 是 `192.168.50.1`。旧 ESP 热点及 `192.168.4.1` 不再是当前入口。电脑只用于开发、发本地 USB 虚拟许可和显示刺激，不中继 Z15→ESP 方向报文。有限测试已经结束，未安装桥接开机服务。真实 API 观察 5 秒没有活动会话，始终发送 STOP，尚未用真实 EEG 做方向选择。

部署前的只读检查历史：初期 COM16 不主动复位探测写超时；之后获授权复位并备份，ROM 全片摘要核验通过。随后另获授权部署 AP 台架、再更新 Station 私有联网配置。原应用已替换，不保留原网页／语音功能；eFuse、Z15 正式代码、模型、PL 和启动服务未改。电脑 Wi-Fi 为开发临时切换至 Z15，已恢复 `JLU.WIFI`；Z15 上仅新增独立测试目录 `/home/xilinx/wheelchair_virtual_20261006`。49 个正式文件散列及采集/网页服务 PID、重启计数前后相同。

部署前完整设备备份：`firmware_backups/com16_20261006_rom_full_03.bin`，16,777,216 字节，SHA-256 `4b056926c447417ee6b9f1d36e461039dbcc261d011662a70d02a7f825a678a1`。与所提供备份的 bootloader、factory 应用和分区表一致，差异页均位于 NVS 配置分区；没有解析其中凭据。完整设备校验记录见 `output/com16_rom_backup_verification.json`，映像审计见 `output/com16_current_flash_audit_20261006.json`。**读取/比对通过不等于已经实测写回恢复。**

## 目前核实了什么

历史 AP 断连检查通过：手机断开热点后，`link_ready` 从 true 变 false，许可撤销、方向 STOP、GPIO 禁用。报告见 `output/network_bench_disconnect_20261006.json`。这不能代替新 Station 的实际掉线/重连测试；本次只验证停止续发时的本地许可过期。重连不自动恢复和实体停车尚未实测。

- 用户提供的 `backup_2.bin` 和 `esp32s3_backup.bin` 完全相同，均为 16,777,216 字节。SHA-256：`fd27dc4ff4b582caa6fe1f640d8aa1a09dc00fb9f15e0a99a5dbdc7d60c3bb70`。
- 文件内有有效的 ESP32-S3 bootloader 和应用映像；分区表在 `0x8000`，MD5 校验通过；factory 应用从 `0x10000` 开始，占用分区 `0x100000`。映像 checksum 和附加 SHA-256 校验通过。
- 应用描述：项目 `LYX`，版本 `1`，编译时间 `Aug 27 2025 18:15:53`，ESP-IDF `v5.5-rc1-dirty`。应用映像实际长度 802,736 字节。
- 应用内的网页按钮为 `start/left/stop/right/back`，对应 `/start`、`/turn_left`、`/stop`、`/turn_right`、`/turn_back`。**这是网页文本与接口绑定证据，不是实际车轮方向或刹车证据。**
- 补充逐按钮解析确认：备份网页的五个请求**全部为 POST**，包括 `/stop`。旧版审计只做短字符串匹配，漏掉一行 HTML 中的停止请求，且没有识别 POST；新报告 `output/firmware_interface_audit.json` 更正该问题，旧报告保留作为历史记录。
- 该备份网页只注册 `onclick`，没有松手发停止的处理、周期定时器或外部脚本。**这是网页层行为，不证明 ESP32 内部没有超时保护；也没有核对当前设备运行页与备份是否一致。**
- 备份内识别到 `ESP32-C3 Car` 页面标题和 `LYX_WIFI` 字符串，没有在已解析应用段找到用户列出的两个小智云端完整 URL。部署前读出的 factory 应用与该备份逐字节一致；这仍不确认原 AI 语音功能是否存在或正常运行。
- 离线 esptool 5.3.1 `image-info` 独立确认 bootloader 芯片 ID 为 9（ESP32-S3）、校验有效。**bootloader 配置的 Flash 容量为 2 MB，备份文件长 16 MiB；二者均不证明实体 Flash 容量，不能按文件大小直接烧录。**
- Windows 枚举 COM16 为 Espressif USB VID `303A` / PID `1001` 的 USB 串行设备。追加获授权 ROM 检查确认 ESP32-S3 QFN56 v0.2、MAC `30:ed:a0:a2:e4:24`、16 MiB Flash。ROM 报告内嵌 8 MiB PSRAM，但未做内存实测；40 MHz 是晶振频率，不是已验证的 SPI Flash 时钟。Secure Boot 和 Flash Encryption 报告为关闭，未修改 eFuse。
- `D:\ican` 本身不是 Git 仓库；`D:\ican\codex_project` 是仓库，已有大量未跟踪工程。本轮只新增 `wheelchair_ssvep` 目录。

原文件完整路径记录在 `output/firmware_audit.json`。为了防止微信临时目录清理，保留一份相同文件到 `firmware_backups/provided_flash_fd27dc4f.bin`，复制后重新核对散列一致。未解析 NVS；该备份可能含配网凭据，不要直接公开上传。它已被本目录 `.gitignore` 排除。

## 分工与暂定映射

### 当前手动动作已能工作

用户在追加照片时确认：当前 `http://192.168.4.1` 网页能正常控制轮椅运动。此项作为用户现场观察记录，未由本包发送命令复验。

用户进一步确认：**必须另点“停止”才停止运动，松开方向按钮并不停。** 无线断开后的行为尚未测试，不能把松手观察直接当成已验证的断网行为。

前期首先评估了复用现有 HTTP 动作接口。随后用户确认无法取得原源码，**授权另写专用控制固件，并接受原网页/语音功能不保证保留**。现已另获授权烧录禁用 GPIO 的联网台架版，采用接收端本机限时许可；没有授权启用 GPIO、重接线或真实动作。照片中的线缆遮挡仍不足以可靠分配每个 GPIO，继续保留未知值。

P1 无自锁只表示驱动板按输入电平工作。**ESP32 若收到一次方向请求后持续维持 GPIO 电平，驱动板仍会持续驱动**，不能因为 P1 无自锁就把无线掉线等同于停车。

进入实体脑控前，优先确认现有 ESP32 的本地运动限时/失联撤销逻辑，及停止后的实际制动。如果已具备且能验证，可以直接保留固件接入；若不具备，必须先补接收端保护或独立硬件限时/使能保护，不能只靠 Z15 之后再发 `/stop`。现有软件原型没有绕过这个关口。

### 追加离线处理函数检查

`inspect_motion_handlers.py` 限定于已核对 SHA-256 的备份，不连接设备；使用现有 Xtensa objdump，按每个函数入口分别反汇编，避免将函数间填充错误解释成指令。没有恢复完整源码，也没有修改 `.bin`。

在备份的初始数据段中，五个 URI 描述符位于 `0x3fc9ab20` 至 `0x3fc9ab60`，结构首四项与 [ESP-IDF v5.5-rc1 HTTP 结构定义](https://github.com/espressif/esp-idf/blob/v5.5-rc1/components/esp_http_server/include/esp_http_server.h) 一致。停止入口为 `0x4200aa98`，方向入口为 `0x4200aad0`、`0x4200ab08`、`0x4200ab40`、`0x4200ab78`。

五个函数都调用 `0x4200b69c`。该公共函数的诊断名称是 `gpio_set_level`，其寄存器置位/清位路径与 [官方 GPIO 实现](https://github.com/espressif/esp-idf/blob/v5.5-rc1/components/esp_driver_gpio/src/gpio.c) 及本机 ESP32-S3 `gpio_ll_set_level` 对照一致。因此可以从指令直接读出备份中的 GPIO10–13 电平组合，记录在 `hardware_profile.json` 的 `offline_backup_gpio_commands` 中；`/stop` 四路均写零。

**这些是程序中的电平，不是已核对的左右端子接线或实体输出测量。** 部署前的 factory 应用已确认与所分析备份一致；当前应用已换成禁用 GPIO 的专用台架版。原方向函数先写四路输出，再回复/打印结果，没有观察到运动许可到期的设置。未审计原应用全体后台任务与断连回调，因此不声称原固件绝对没有超时保护；仍没有足够证据启用实体脑控。

反汇编原始输出保留在 `output/motion_handler_disassembly.txt`。重复检查可运行 `python inspect_motion_handlers.py`；它只读取备份及生成/核对隔离的 IROM 分析副本，不执行 ESP 指令。

要保留现有功能，首选取得原工程，在 ESP32 本地统一管理网页/脑控意图，增加有限运动许可、失联撤销、转向中立间隔与独立急停。拿不到源码时，选择独立硬件保护或授权另写控制固件；不能承诺直接给 `.bin` 打补丁就能保留全部功能并完成安全验收。

### 后续硬件声明（2026-10-06）

用户进一步提供：GPIO10、11、12、13 与两根 GND；驱动板标称 **30 A、24 V、P1 点动／桥驱无锁**。原文“P1电动”按所附说明中的“P1点动”理解，并保留在 `hardware_profile.json` 中。30 A 是用户提供的模块标称值，不是已验证连续电流、启动/堵转能力或轮椅制动能力。

根据用户所附 QF-M05S 说明，P1 是非自锁模式：两个控制输入都低时，电机输出开路；一高一低分别对应模块正/反转；两个都高时，说明称作“急停”。这些是资料中的逻辑组合，**不等于已经验证的 ESP GPIO 电平或车轮方向**。输入电压门限、COM 的实际接法、左右板 K1/K2 与四个 GPIO 的对应关系仍未知，不能直接填入动作程序。

无自锁模式适合后续“有效指令持续许可，失去许可就撤销驱动”的设计；但电机开路可能滑行，资料中的电气停机也不是独立机械刹车或物理急停。ESP32 断电、复位后的控制输入和实际停车过程仍须在无人受控台架验证。

24 V 指电机模块供电，**不是 GPIO 控制电压**。ESP32-S3 是 3.3 V 逻辑系统，控制端必须核实兼容性，不能将 24 V 或未知的控制端电压直接送进 GPIO。参考 [ESP32-S3 官方电气规格](https://documentation.espressif.com/esp32-s3_datasheet_en.pdf) 第 5 章。继电器模块不采用高频 PWM 来“调低车速”；本阶段不实现速度控制。

`hardware_profile.json` 仅作隔离硬件声明记录，动作代码不加载它；具体端子和安全 GPIO 组合保留 `null`，新固件 GPIO 输出仍禁用。资料图片保留在 `hardware_refs/`；硬件资料记录阶段未打开 COM16，之后仅在获授权的动力隔离检查中使用串口复位/读取，不改现有接线、不烧录固件、不调用运动接口。

Cyton 原始 EEG → Z15 上已有 SSVEP 检测/质量门控 → Z15 上方向与通信状态机 → ESP32 本地运动许可/超时/急停 → 经核实的电机驱动。

PC 负责显示四角刺激和开发；COM16 是开发接口，不要求最终运行时依靠电脑串口。SSVEP 检测和业务状态机留在 ARM，不为这一步修改 PL。

保持现有页面四角位置与频率不变，`mapping.json` 暂定：

- 左上 8 Hz → 前进 → 旧接口参考 `/start`。
- 右上 10 Hz → 后退 → 旧接口参考 `/turn_back`。
- 左下 12 Hz → 左转 → 旧接口参考 `/turn_left`。
- 右下 14 Hz → 右转 → 旧接口参考 `/turn_right`。
- 未识别、数据过期、质量不合格、显示时序不合格、会话停止 → 请求停止。

映射可以调整，但 `mapping.json` 必须完整包含四个频率，并且四个方向各出现一次。上述旧接口方法参考均为 **POST**；`/turn_back` 是否实际是倒车、GPIO 是否保持方向电平、停止是否断电或刹车，都要另行核实。

### 识别边界

已有 `pynq_guardianloop/ssvep_free.py` 明确声明 `control_enabled=False`、`production_eligible=False`、`idle_classifier_validated=False`。8/14 Hz 和可靠休息拒绝尚未完成实体控制验证。

本包没有改变这些标志、没有降低阈值，也没有把 `accepted` 解释为“适合载人行驶”。看中央不闪区域**不等于可靠的停止开关**，误识别仍可能发生。情绪、疲劳、运动想象不参与这套行驶命令仲裁。

## 可运行的方向预览

`dry_run_bridge.py` 只有两类 IO：读取 SSVEP JSON 和向终端打印结果。没有 ESP32 运动写入、串口写入、自动启动刺激或修改脑控服务的代码，也没有“开启实体控制”的参数。

合成演示（不用戴帽，不联网）：

```powershell
& 'D:\ican\codex_project\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 'D:\ican\codex_project\wheelchair_ssvep\dry_run_bridge.py' --demo
```

只读观察现有 Z15 API（要先有正常运行的自由选择会话；不由这个脚本启动）：

```powershell
& 'D:\ican\codex_project\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 'D:\ican\codex_project\wheelchair_ssvep\dry_run_bridge.py' --source-url 'http://192.168.50.1:9102/api/ssvep-free' --seconds 30
```

也可将上面的来源换成 `http://192.168.2.99:9102/api/ssvep-free`。程序只允许明确的私网/回环 IP、端口、这个精确路径；拒绝重定向、代理、URL 凭据、查询参数、运动接口路径。`legacy_route_reference` 是参考字符串，**从不请求该 URL**。

输入检查包含：采集端来源、会话、显示时序、已确认候选、质量、输入年龄加本次请求耗时不超过 0.5 秒、有效决策、0.55 分数/0.10 差值下限。窗口停滞超过 0.45 秒或窗口索引不连续也撤销预览。

`preview_direction=stop` 只表示软件请求，不表示真实轮椅已停车。输出始终带有 `physical_output_enabled=false`、`motor_command_sent=false` 和 `current_motor_state=not_observed`。

2026-10-06 的 2 秒只读连接尝试未获得可用快照，预览保持 stop；未因此更改网络或服务。合成映射通过不等于已完成板端实时联调。

## ESP32 接收保护原型

`receiver/motion_guard.c/.h` 是可嵌入的 C 状态机，没有 GPIO/HTTP。固件将同一核接入单一控制任务、HTTP 鉴权、断连撤销和串口台架许可。公开源码默认电机 GPIO 禁用、网络凭据为空；当前上板应用使用被忽略的 Station 私有配置，仍禁用 GPIO。物理输出分支只做过假电机软件测试，未在设备启用。

工程台架初始限制如下；它们不是经过轮椅制动距离或继电器寿命验证的参数：

- 上电默认不允许运动，必须通过本地人工许可；网络命令不能自行解锁。
- ESP32 按本机单调时钟签发单次 ticket，300 ms 后失效。接收端基于签发时间到期，不因迟到报文再获得完整 300 ms。ticket 不是身份认证密码。
- boot ID 必须每次启动唯一，序号不能重复或回绕。旧启动、旧票、重复票和非法方向失败停机。
- 数据续期必须不断得到新的票并收到对应指令；单纯请求票不会延长正在进行的运动。
- 换方向先输出 STOP，至少保持 300 ms 中立；不排队自动执行之前的转向。
- 无论是否续期，一次本地许可后的运动台架 burst 最长 1000 ms；到期停机并要求再次本地人工许可。此模式刻意不提供连续行驶。
- STOP 不需要有效票，急停锁定优先于运动；急停只能由本地确认清除，清除后仍未解锁。

这些措施只在 `wc_tick()` 实际得到调度、GPIO 绑定正确、电机控制器执行 STOP 时才有作用。ESP Timer 的任务回调可能被更高优先级任务和 Flash 操作延迟，软件定时器不是硬件急停保证。参考 [ESP Timer 官方文档](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/esp_timer.html)。

接入现有 ESP 固件时必须做到：

1. 所有输出由同一控制任务串行拥有；HTTP、语音、串口、网页按键都只提交意图，不再直接改电机 GPIO。必须消除绕过保护的旧路径。
2. 启动 GPIO 初始化就保持经核实的安全状态；核实继电器有效电平、方向组合、机械/电子刹车。不能默认“所有 GPIO 拉低”就是安全停车。
3. 高频检查到期、Wi-Fi 断开和驱动故障；本地物理急停应能独立切断驱动使能/电源，固件卡死与复位也应落在安全状态。实际超时和制动时间须实测。
4. 提供经过配对/认证的接收通道、状态查询、ticket、命令和停止接口；HTTP 返回成功只证明命令受理，不能冒充车轮已停止反馈。新增台架固件已有静态 key 和有限许可协议，但 HTTP 未加密，仅作私有隔离网络开发，不是经过安全认证的通道。
5. 旧 `/start` 等接口不能继续提供不受约束的锁存运动。若要保留旧页面，需要将它们纳入同一个仲裁器；不验证前禁止与脑控并行争抢。

不应仅在 Z15 执行 `POST /start`，延时后再 `POST /stop`：网络丢失后后一条可能永远到不了。现有备份是否有本地失联停机尚未知，不能假定已经安全。

## 网络安排

`bench_network_bridge.py` 使用同一 `DirectionPreview` 门控，通过鉴权 ticket／command 发送虚拟方向，通过 `/api/stop` 撤销；只接受预期产品、GPIO 禁用、`bench_only` 接收端，拒绝代理/重定向，不提供网络解锁或 GPIO 启用。坏质量、断流、旧窗口仍撤销，模型与阈值不变。42 项 Python 回归通过，其中 18 项发送端测试亦在 Z15 通过；发送端已上传独立目录，实际板间八用例通过。

Z15 当前使用 `wpa_supplicant` AP 与 `dnsmasq` DHCP。已私下读取原热点凭据并写入 ESP 忽略的配置，没有输出密码/key或更改 Z15 配网。接收 IP 根据 Z15 `wlan0` 邻居表中 ROM 已核对的 ESP MAC 唯一匹配，再检查鉴权产品响应；不把 TCP 连通或任意 IP 当身份依据。第一次运行因误按 ISC DHCP 查租约而在测试前终止；修正为已验证的邻居匹配后通过。失败记录 `_01` 和成功记录 `_02` 均保留。

后续桥接只运行有限测试，不修改开机服务。私有配置包含 `receiver_url` 和 `auth_key`，应在被忽略的本机 `build/` 或板端独立测试目录保存、限制访问，不能复制进共享源码。命令示例仅在完成接收端身份及网络核对后使用：

```text
python3 bench_network_bridge.py --config /ABSOLUTE/PRIVATE/receiver_private.json --source-url http://127.0.0.1:9102/api/ssvep-free --seconds 30
```

该程序从不自行 ARM。当前 ESP32 的一次人工许可仍只允许最长 1 秒虚拟 burst；网络错误后没有自动解锁。STOP 请求提交成功不是实体停车反馈。可运行 `python -m unittest -v test_network_bridge test_bridge test_audit_firmware` 重现 42 项 Python 检查。

当前使用 ESP32 Station → `GuardianLoop-Z15`，不依赖电脑网络中继，不提供原语音云服务。旧 AP 应用已保存在 `build/ap_bench_901568_ac5fb529.bin`，散列 `ac5fb529de71572e9562ef4a716bae122fe0d3e8980d2bdfedfd93f17f7a4d07`；原私有 AP 配置保存在 `build/ap_bench_config_private_before_station.h`。`build/wifi_connection_private.md` 仅为旧 AP 历史连接说明。新旧二进制、配置和全片备份均可能含凭据，不放入公开/队友源码包。写回恢复未实测。

## 测试与复现

Python 方向映射/撤销：16 组 unittest 已运行通过。合成四方向和停止示例已运行。

新增 `test_audit_firmware.py` 的 8 组测试已通过，检查单行网页中五个 POST、停止请求、松手事件、动态方法与不允许的路由。可与映射测试一起运行：`python -m unittest -v test_bridge test_audit_firmware`。离线网页解析不执行 JavaScript，也不访问任何动作地址。

```powershell
Push-Location 'D:\ican\codex_project\wheelchair_ssvep'
& 'D:\ican\codex_project\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 -m unittest -v test_bridge
Pop-Location
```

接收 C 核和 C 测试文件已用电脑现有 ESP32-S3 GCC 14.2.0 交叉编译，`-Wall -Wextra -Werror -pedantic` 通过，无新增依赖。产物仅 `.o`，不是完整固件。

```powershell
& 'C:\Users\lenovo\AppData\Local\Arduino15\packages\esp32\tools\esp-x32\2601\bin\xtensa-esp32s3-elf-gcc.exe' -std=c11 -Wall -Wextra -Werror -pedantic -c 'D:\ican\codex_project\wheelchair_ssvep\receiver\motion_guard.c' -o 'D:\ican\codex_project\wheelchair_ssvep\build\motion_guard_esp32s3.o'
```

`receiver/test_motion_guard.c` 的 16 组假电机测试已在电脑现有 WSL Ubuntu 24.04、GCC 13.3.0 中运行通过。Windows MinGW 缺少 `cc1`，没有为此安装工具。以下命令可复现：

```powershell
wsl.exe -d Ubuntu-24.04 --exec gcc -std=c11 -Wall -Wextra -Werror -pedantic /mnt/d/ican/codex_project/wheelchair_ssvep/receiver/motion_guard.c /mnt/d/ican/codex_project/wheelchair_ssvep/receiver/test_motion_guard.c -o /mnt/d/ican/codex_project/wheelchair_ssvep/build/test_motion_guard_linux
wsl.exe -d Ubuntu-24.04 --exec /mnt/d/ican/codex_project/wheelchair_ssvep/build/test_motion_guard_linux
```

离线固件格式参考：[Espressif 映像格式](https://docs.espressif.com/projects/esptool/en/latest/esp32s3/advanced-topics/firmware-image-format.html)、[分区解析器](https://github.com/espressif/esp-idf/blob/v5.4.2/components/partition_table/gen_esp32part.py)、[应用描述结构](https://github.com/espressif/esp-idf/blob/v5.4.2/components/esp_app_format/include/esp_app_desc.h)。审计工具只输出允许的元信息和小车路由，不打印 NVS/任意字符串。

新增 `receiver/command_wire.c/.h` 的严格定长命令解析和 `test_command_wire.c` 的 7 组测试：五个指令、64 位标识、无票 STOP、非法/残缺输入、离线备份电平模式、到期/禁止自动重启。解析后仍经过同一接收核，不直接写 GPIO。

软件共 65 项检查通过（42 Python、16 假电机控制核、7 报文/模式 C），23 项 C 曾在 ASan/UBSan 下通过；本次重跑的是 42 项 Python。另有历史 19 项 USB 虚拟检查、本次 8 项 Z15→ESP 实际鉴权网络用例；不要混作真实轮椅动作次数。真实 GPIO、制动和真实 EEG 选择仍未验收。当前部署以 `output/station_bench_deployment_20261006.json` 为准。

## 下一个实体关口

用户已确认目前只有两份 `.bin`，并声明四个 GPIO 及 30 A／24 V／P1 无自锁规格；已提供 QF-M05S 说明截图。当前 Flash 中主程序身份和实体 Flash 容量已核对，完整备份已校验。还缺：四个 GPIO 分别接左右驱动板 K1/K2 的准确对应、两个 GND 的目标端子、输入门限/有效电平与 COM 接法、左右电机极性、实际模块与说明的匹配、安全停止及刹车验证、独立急停、PSRAM 内存实测、SPI Flash 时钟核实。

COM16 已运行禁用 GPIO 的 Station 应用，直连及虚拟五指令已通过。下一步是保持动力隔离，用真实 SSVEP 验证四方向和看中央非闪区域时的撤销/误触发，并补 Station 实际掉线/重连检查；不自动开启刺激或要求立即佩戴。原语音/OLED/OTA 未保留，恢复写回尚未实测。启用 GPIO 或接回电机属于另一个关口，不在本次授权范围。

验证顺序：

1. 接收端本地软件测试 → 电机动力断开、无人员乘坐时核实信号与保护 → 再做无人受控空载方向/停止测试。每一步明确授权后才进行烧录或驱动动作。
2. 检查网络断开、Z15 程序退出、ESP32 卡顿/复位、重复/迟到命令和语音/网页冲突，确认不会自行继续或恢复行驶。
3. 先做 SSVEP 虚拟选择与独立确认，包含中央非闪区域和不看目标；记录误触发和拒绝，尤其 8/14 Hz。不能用提示答案冒充识别输出。
4. 通过后才考虑带独立物理运动许可、人工急停、受控场地的非载人演示。**本包不构成载人轮椅安全验收，也不能用于未经评估的载人行驶。**
# 2026-10-15 当前状态

已部署与原 GPIO 映射一致的实际输出**测试版**，默认源码配置仍保持禁用，启用配置只在私有构建目录。手机与真实 HDMI SSVEP 发送接口已支持显式选择该身份，未加入网络 ARM。用户确认动力断开期间，手机短指令、本机租约撤销和软件急停检查通过；真实车轮方向/停车、佩戴识别和载人运行尚未验收。见 [实际输出接入记录](../docs/WHEELCHAIR_MOTOR_TEST_20261015.md)。以下保留历史开发记录，不能把其中旧“GPIO 禁用”状态当作当前上板版本。

