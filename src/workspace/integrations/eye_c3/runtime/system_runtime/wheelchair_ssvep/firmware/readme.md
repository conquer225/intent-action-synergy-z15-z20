# ESP32-S3 轮椅接收固件（持续遥控／台架配置）

现场更新：用户随后报告四个方向实际只出现右转／后退，实体方向验收失败。已刷入原版输入＋输出模式的 GPIO 配置及独立引脚读回修正版；断动力下四方向要求／输入读回全部一致、STOP 与失联保护通过，车轮实际方向仍待无人架空复测。不能把断动力回执视为方向已现场正确。最新状态见 [GPIO 排查与修正记录](../../docs/WHEELCHAIR_GPIO_READBACK_20261015.md)。

2026-10-15 持续遥控已部署：手机点方向后通过前台心跳维持接收端 500 ms 手动租约，不设正常运行总时长；STOP/失联/页面退出撤销，重连不自动恢复，不需逐次串口 ARM。正常页面 15 秒持续指令与两级失联撤销的断动力检查通过，尚未验收实体停车或载人驾驶。本机 ARM 与 SSVEP 仍保留原限时行为。完整证据见 [持续遥控记录](../../docs/WHEELCHAIR_REMOTE_CONTROL_20261015.md)；以下 motor-test 说明是此前的短动作版本。

2026-10-15 更新：在用户确认原接线未变、无人架空、独立断电手段及动力已断开后，已部署单独身份的 **motor-test 实际 GPIO 输出测试版**。默认共享/私有台架源码配置仍禁用 GPIO；启用构建保存在忽略的 `build/motor_test_20261015`，不公开凭据。原 GPIO 映射、限时许可、串口本机 ARM、断网撤销和停止逻辑复用，未开放自动网络解锁。仅完成断动力指令通路和本机租约验证，尚未验收真实车轮/载人运行；详细证据见 [实际输出接入记录](../../docs/WHEELCHAIR_MOTOR_TEST_20261015.md)。下文 2026-10-06 是历史台架基线。

COM16 ESP32-S3 已运行 Station 台架固件，加入 Z15 原热点；**`motor_gpio_enabled=false`，不初始化/写电机 GPIO，动力继续隔离**。Z15 直发虚拟五指令及异常撤销共八用例通过。原语音、OLED、OTA 和动作页面不保留。16 MiB 原备份已核验，写回未实测。当前记录见 `../output/station_bench_deployment_20261006.json`；历史 AP 部署记录仍保留。

源工程：`guardianloop_wheelchair/`。`libraries/WheelchairGuard` 直接编译本包 `receiver/` 中经过假电机测试的 C 核，没有另存一份状态机。复制工程时须保留整个 `wheelchair_ssvep` 目录，而不是只复制 `.ino`。

## 已实现的边界

- 默认 `WC_ENABLE_MOTOR_GPIO=0`，不初始化、不写 GPIO10–13；Wi-Fi 凭据与认证 key 均留空，默认不启动 Wi-Fi 或网页。
- 本地 USB 串口 `ARM` 才能许可；网络不能解锁。首次方向命令受理后，一轮最长 1000 ms；到期、STOP 或失联后不会自动恢复，需再次本地许可。USB 开发指令不是独立物理急停，最终脱离电脑运行的本地许可硬件还未接入。
- 接收端本机签发一次性 ticket，签发后 300 ms 到期。迟到命令不重新获得完整许可时间，续期不延长一轮 1000 ms 上限；请求 ticket 本身也不续期。
- 换方向先 STOP，至少 300 ms 中立，需要新的有效命令才能继续，旧转向不排队自动执行。保持同方向续期不反复切换机械继电器。
- 控制核仅由一个高优先级任务拥有；HTTP、串口和 Wi-Fi 回调通过队列或停止标志提交请求。队列中的动作超过 100 ms、被新停止事件撤销、非法/重复/过期票等都拒绝并撤销许可。
- Wi-Fi 断开请求 STOP；`ESTOP` 软件锁定，`CLEAR` 只清软件锁定而不解锁。GPIO 故障不能通过 `CLEAR` 解除。
- 原 `/start`、`/turn_back`、`/turn_left`、`/turn_right` 的 POST 返回 410 并请求停止，不能绕过许可；网页仅有状态和停止按钮。

这里的 10 ms 控制循环和 300 ms 许可是软件设计参数，**不是实测停车时间或硬件保证**。调度饥饿、控制器失效、电源故障、接线/驱动问题仍可能使软件停机失效；继电器断开也不证明轮椅已刹住。

## 五个意图如何分工

ARM 保持原四角映射：8 Hz 前进、10 Hz 后退、12 Hz 左转、14 Hz 右转；没有新的可信方向、信号/质量/时序失效、会话停止时撤销方向。ESP32 只接收方向和有限许可，不计算脑电。PL、情绪、疲劳、运动想象、眼控均未修改。

**不看闪烁不是已经验证的第五类别，也不能作为唯一急停。** 300 ms 是 ESP 许可时限，不是“移开视线到停车”的上限。`dry_run_bridge.py` 只预览；独立 `bench_network_bridge.py` 已能从 Z15 发虚拟命令，但 SSVEP 正式控制资格未开启。合成通信检查不替代真实四方向、中央非闪区域的误触发与撤销延迟测试。

## 隔离协议

以下是网络接口说明。历史 USB 虚拟检查通过；当前鉴权 Wi-Fi 指令亦已由 Z15 实际发送并通过八用例，见 `../output/direct_network_acceptance_20261006_02.json`。这些仍是 GPIO 禁用的虚拟意图，不是实体动作。

- `GET /`：本地静态状态页，无方向启动按钮。
- `GET /api/status`：`armed`、`software_estop_latched`、`requested_direction`、`motor_gpio_enabled` 等状态。`current_motor_state=not_observed`，不伪装车轮反馈。
- `POST /api/ticket`：空 body，必须带 `X-WC-Key`；返回 boot ID、sequence 和本机到期毫秒数，未许可返回 409。
- `POST /api/command`：同一 key；ASCII body 为 `16位十六进制boot_id 空格 16位十六进制sequence 空格 direction`。direction 严格为 `stop/forward/backward/left/right`，无换行、尾空格或额外字段；数字用固定宽度字符串避免浮点精度问题。
- `POST /api/stop` 与 `POST /stop`：无 key 也允许请求停止。202 只表示停止请求已提交，**不表示观察到实体停车**。

启动/动作鉴权是私有网络内的静态 key；HTTP 未加密，不具有防主动攻击的安全认证，不能暴露公网、公共 Wi-Fi 或用来宣称系统安全。无鉴权 STOP 可被局域网设备用于拒绝服务，但不能启动车辆。

私有配置只保存在忽略的 `guardianloop_wheelchair/config_private.h`，当前设 `WC_STA_SSID=GuardianLoop-Z15`、原热点密码和独立 64 位小写十六进制 key。它们未打印或公开。当前接收地址观察为 `192.168.50.72`（DHCP，可能变化）；旧 `192.168.4.1` 入口已停用。原 AP 配置/映像保留在忽略的 `../build/`；`wifi_connection_private.md` 仅是旧 AP 历史说明。私有配置、备份和含凭据产物不加入公开/队友源码包。Z15 独立目录的私有 JSON 权限为 0600、目录 0700。

## 板上虚拟检查

`../bench_serial_check.py` 首先核对产品身份、`bench_only`、GPIO 禁用及电机状态未观测，再允许本地虚拟许可。19 项 USB 检查通过，涵盖四方向、300 ms 到期、重放撤销、1 秒 burst、软件急停锁定和 STOP 收尾；报告见 `../output/network_bench_serial_protocol_20261006.json`。`--disconnect-check` 仅在方向保持 STOP 时等待 AP 客户端离开，检查虚拟许可撤销，不测实际停车时间。

`STATUS`、`TICKET`、`CMD <协议 body>` 是仅在禁用 GPIO 的构建中存在的本地诊断指令；GPIO 启用构建不包含这些诊断入口。它们复用 HTTP 的解码器、状态返回和单一控制任务，不另写控制核，也不替代网络鉴权验证。本地 `ARM/STOP/ESTOP/CLEAR` 不是独立物理安全装置。

追加 AP 断连检查已在板上通过：手机 Wi-Fi 断开获用户确认，串口观察到 `link_ready=false`、未许可、STOP、GPIO 禁用。报告见 `../output/network_bench_disconnect_20261006.json`。测试没有发送方向命令，不验证车轮停车时间，也不声称已经实测重连后的行为。

新 Station 直连检查：8/10/12/14 Hz 合成来源对应前进/后退/左/右，另有 STOP、无数据、坏质量、过期输入，共八项通过。四方向停止续发后 0.45 秒检查点均未许可/STOP。Z15 上 18 项发送端测试通过；真实 API 观察 5 秒缺少会话，仅发 STOP。未安装常驻桥接服务，测试已结束。Station 的实际掉线/重连、真实 EEG 方向选择和物理输出均未测试。

## 本地编译，不上传

使用电脑已经安装的 Arduino CLI 0.35.3、Arduino-ESP32 3.3.11、Xtensa GCC 14.2.0，无新增依赖。以下命令没有端口参数或 upload 操作：

```powershell
& 'C:\Users\lenovo\AppData\Local\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe' compile `
  --fqbn 'esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,PSRAM=disabled,FlashMode=dio,PartitionScheme=custom' `
  --libraries 'D:\ican\codex_project\wheelchair_ssvep\firmware\libraries' `
  --build-path 'D:\ican\codex_project\wheelchair_ssvep\build\arduino_network_bench' `
  --build-property 'build.flash_size=2MB' `
  --build-property 'upload.maximum_size=1048576' `
  --build-property 'compiler.c.extra_flags=-Werror' `
  --build-property 'compiler.cpp.extra_flags=-Werror' `
  --warnings all `
  'D:\ican\codex_project\wheelchair_ssvep\firmware\guardianloop_wheelchair'
```

当前 `partitions.csv` 保持原 factory `0x10000`、容量 `0x100000`，编译上限为 1 MiB；PSRAM 禁用。实体 Flash 已通过 ROM 检查为 16 MiB，但本轮沿用原应用的 Flash 头 `021f`（声明 2 MB），没有据物理容量改写头部。上述命令只编译；实际获授权烧录只写应用，并使用 `flash-mode/frequency/size keep`，未上传新 bootloader、分区表或 Arduino merged 文件。不要把自动生成的整合映像拿来覆盖原布局。

当前 Station 编译／链接通过：程序 901,465 字节，应用映像 901,616 字节，静态 RAM 44,696 字节，适配原 1 MiB factory；写后摘要及运行身份检查通过，最终联网/未许可/STOP/GPIO 禁用。旧 AP 映像 901,568 字节已另存 `../build/ap_bench_901568_ac5fb529.bin`；原网络关闭基线 424,752 字节仅作历史编译检查。

当前产物在 `../build/arduino_network_bench/`，散列和部署记录见 `../output/station_bench_deployment_20261006.json`。软件/历史记录见 `../output/verification.json`。Arduino 插入的 `#line` 和行尾使私有配置原始散列不同，去该指令并统一行尾后与编译副本一致；GPIO 禁用已确认。运行产品标识为 `guardianloop-wheelchair-bench-0.1.0`，不使用 Arduino 应用头的 `arduino-lib-builder` 作为产品身份。

## 下一次硬件测试前

直连和鉴权虚拟五指令已通过。下一步保持动力隔离，验证真实 SSVEP 虚拟选择与 Station 实际掉线/重连，仍不能开启电机。PSRAM 仅有芯片报告，Flash 时钟上限未独立核实；不要依赖网页“停止”作为动力隔离。原 AP 应用与原全片备份均保留，写回未实测。

当前设备副本为 `../firmware_backups/com16_20261006_rom_full_03.bin`，16,777,216 字节，SHA-256 `4b056926c447417ee6b9f1d36e461039dbcc261d011662a70d02a7f825a678a1`。ROM 全片摘要比对通过；记录见 `../output/com16_rom_backup_verification.json`。原提供副本 `../firmware_backups/provided_flash_fd27dc4f.bin` 另行保留，bootloader、主程序及分区表相同，差异页只位于 NVS。两份文件可能含私密配置；未解析 NVS，也没有进行写回恢复测试。

启用电机 GPIO 前，还必须核实 GPIO10–13/左右 K1/K2、有效电平与电压兼容、上电/复位状态、实际停止/制动和独立物理急停。`WC_ENABLE_MOTOR_GPIO=1` 如没有同时设置两项核实开关会编译报错；设置开关本身不能代替核实。当前四路电平来自离线备份反汇编，不能据此保证当前接线/方向/制动正确；固件不会自行改变接线。

这版没有速度调节、避障、碰撞检测或载人安全验收，不用于载人行驶。所有真实方向和故障测试均须独立授权、在受控无人台架执行。
