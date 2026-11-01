# 轮椅错向：原版初始化对齐与引脚读回

## 现场报告和边界

用户在持续遥控版本上报告：前进按钮实际右转、左转按钮实际后退、右转按钮实际右转、后退按钮实际后退。**四按钮没有对应四种实体动作，方向验收失败。** 此报告优先于此前仅有软件回执的回归结果。此前一次前进短动作的现场反馈不能证明此后四方向都正确。

用户再次提供 `backup_2(1).bin`、`esp32s3_backup(1).bin`，确认是最早 `192.168.4.1` 能正确控制方向的程序。两个文件 SHA256 均为 `fd27dc4ff4b582caa6fe1f640d8aa1a09dc00fb9f15e0a99a5dbdc7d60c3bb70`，与已保存原备份一致。

此次用户已明确要求进行下一步，并再次回复“动力已断开”。只在电机 24V 动力断开、ESP32 USB 供电的边界内更新及做引脚检查，不自动恢复动力、不进行实体动作。

## 已确认／推断／未知

- 已确认：原版 `/start`、`/turn_back`、`/turn_left`、`/turn_right` 的四路最终电平与当前 `backup_gpio_pattern.h` 一致。GPIO10/11/12/13 顺序分别为 `0011`、`1100`、`1001`、`0110`；STOP 为 `0000`。不交换按钮名、不猜新映射。
- 已确认：原备份初始化 `0x4200aeb3..0x4200aecc` 向 `0x4200b790` 传入 GPIO10/11/13/12、模式值 3；该函数诊断字符串为 `gpio_set_direction`，对应输入＋输出。新程序原先仅调用 `gpio_set_direction(..., GPIO_MODE_OUTPUT)`。
- 推断：完整 GPIO 功能／输入输出配置可能与现场差异有关；仅发现不同不等于证明错向根因，更不能直接判硬件损坏。
- 未知：当前 GPIO 到两侧驱动端子的对应、驱动器输入响应和每个车轮的实际方向。GPIO 内部数字读回不测电压，也不证明继电器／电机响应或制动。

## 最小修改

`firmware/guardianloop_wheelchair/motor_gpio.h` 从现有控制器中抽取同一 GPIO 实现供固件和假驱动测试共用。四路先清零，再用 `gpio_config` 显式配置 `GPIO_MODE_INPUT_OUTPUT`、禁用内部上下拉和中断，再清零；保留原方向掩码、切换全低和同方向续期不切继电器。

`controller.cpp` 在同一运动 owner 内取样，状态新增：

- `gpio_profile=input_output_v1`
- `gpio_pin_order=[10,11,12,13]`
- `gpio_requested_bits`：程序已请求的输出组合
- `gpio_input_bits`：四脚输入读回，不再用程序请求冒充读回
- `gpio_readback_available`：GPIO 输出构建为真，禁用台架构建为假

扩展 JSON 缓冲到 768 字节，保留固件身份、手机 API、联网、手动 500 ms 续期、手机 750 ms 心跳、STOP、ESTOP 和脑控门控。未改 Z15 页面、眼控、脑电模型或 PL。

ESP-IDF GPIO 文档说明，`gpio_config` 显式配置 GPIO，`gpio_get_level` 需要输入使能才能读输入值；因此先启用读回条件，再观察，不能把未使能输入时的零值判为坏脚。[官方 GPIO 文档](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32s3/api-reference/peripherals/gpio.html)

## 软件验证和回退

原 65 项 Python、JS、C 19 组控制核和 7 组协议回归通过。新增 4 组 GPIO 假驱动测试，在 Z15 使用 g++ 编译、运行通过；只调用假 GPIO，不操作真实引脚。覆盖先清零再配置、五种电平、强制某脚低的独立读回，以及清零／配置失败不能继续高电平输出。

Windows 的旧 MinGW 缺少 cc1plus，WSL 未安装 g++，未安装新依赖；使用板端已有编译器完成上述测试。证据 `wheelchair_ssvep/output/gpio_readback_20261015/gpio-host-tests.json`，隔离目录 `/home/xilinx/gl-gpio-readback-20261015-wdoGsp`。

回退镜像：`wheelchair_ssvep/build/remote_control_20261015/rollback_before_gpio_readback/guardianloop_wheelchair.ino.bin`，SHA256 `2cd1e0a40ceb8c17dd3e7ba88f87e117202ddbe3a921c50cd0f8914699c8de01`。该文件是修改前已部署的持续遥控应用，不是原厂全片备份。只更新 factory 应用 `0x10000`，不写引导器、分区表、NVS、PHY 或 eFuse；必要时断动力后写回此应用。它有已报告的错向风险，不将回退视为实体方向修复。

## 已刷写：断动力下四方向引脚读回通过

应用编译成功：程序占用 901,981 字节，静态 RAM 44,664 字节；生成应用 902,128 字节，SHA256 `b8558cb762df6db51977454c7132f125b5e09c49402080ecdc1beed5688d3e10`。镜像芯片类型、校验和、附加 SHA、原分区容量和 flash 头均核对通过。

先读回核对 COM16 MAC、更新前应用和原引导/分区表摘要，均匹配。然后只向 `0x10000` 写入该应用，工具报告 11.1 秒写入、写后摘要核验成功，并复位启动。未写 merged 镜像、引导器、分区表或 NVS。`gpio_profile=input_output_v1` 和输入读回接口已在运行程序上确认。

按用户已确认的动力断开条件，经原手机 API 和原 Z15 发送程序进行有限回归。四方向请求值／芯片输入读回均一致：前进 `0011/0011`、后退 `1100/1100`、左转 `1001/1001`、右转 `0110/0110`；停止 `0000/0000`。这是输入采样，不是把 requested 字段复制为输入。原按钮和电平映射没有交换。

同轮保留保护检查通过：手机 STOP 后约 0.249 秒观察到未许可/STOP；手机心跳停止后约 0.943 秒观察到撤销；暂停发送进程后约 0.719 秒检查点已由接收端撤销，恢复进程不自动重新许可。数字是 HTTP/状态检查点，不是车轮实际刹停时间。结束时 GPIO 读回 `0000`、未许可、手动租约关闭，未报告 GPIO 写入故障。

本次没有重启 Z15 网页、HDMI 或采集，原 88 项启动 pin 继续核验。**软件和芯片引脚输出检查已通过，但不能据此认定此前错向根因已唯一确定，不能声称车轮方向修复已现场验收。** 下一步只能先无人架空、独立断电手段在手，逐项确认实际方向和手机 STOP，再讨论载人。

证据目录 `wheelchair_ssvep/output/gpio_readback_20261015/`：`preflash.json`、`image-audit.json`、`flash.json`、`startup-readback.json`、`gpio-regression.json`、`final-state.json`。固件和私有配置在忽略的构建目录内，不公开其联网凭据。
