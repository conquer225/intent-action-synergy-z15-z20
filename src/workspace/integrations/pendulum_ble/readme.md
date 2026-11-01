# 我们意念合一：倒立摆蓝牙接入

本更新让倒立摆通过 DX-BT24 BLE 控制，保留灵巧手、眼控页面、媒体、脑电模型和 STM32 控制协议。链路为 Z15 现有 Wi-Fi 热点 → S3 TCP 9000 → S3 蓝牙 → DX-BT24 → STM32 UART1。Z15 当前系统没有可用蓝牙 HCI 接口，蓝牙主机由已有 S3 承担。S3 与 DX-BT24 之间无线连接。

## 接线

先断电再接线，依据排针丝印，不依据照片方向。

| DX-BT24 载板 | 连接 |
| --- | --- |
| RXD | STM32 PA9，UART1 TX |
| TXD | STM32 PA10，UART1 RX |
| GND | STM32 GND 与独立 3.3V 电源负极，共地 |
| 3.3V | 独立 3.3V 电源正极 |
| 5V、STATE | 悬空 |

USB-TTL 不再接模块 RXD/TXD。C3、ESP8266 不接入这对串口，也不与 DX-BT24 同时驱动 PA10。S3、Z15、灵巧手原接线保留；S3 COM27 只用于调试和本次烧录。用户实物的 STM32 与电机共用供电，烧录 S3 时倒立摆整体断电、手端舵机断电，S3 独立供电保持。

## 源码与构建

`firmware/MultiControlS3/` 是隔离的蓝牙版。手端/RF/映射/校准实现和 TCP 命令沿用外设工程；倒立摆接入替换 PendulumLink，增加会话逻辑、蓝牙配置及状态字段。2026-10-21 修订另修正 GloveRadio.cpp 的重连计数同步：仅在安全张开探测时学习前方接收序号，不因接收端启动旧应答而倒退发送序号；学到的旧应答不直接作为就绪证据。开合姿态、映射和校准数据保留。BootConfig 默认保留手端自动启动，倒立摆需人工启用。C3/ESP8266 原网桥及 S3 UDP 适配源码保留在 `fallback_c3/`，运行时不会自动切回。

使用现有 Arduino-ESP32 3.3.11、ArduinoJson 7.4.2、RF24 1.6.2。复制并填写 WifiConfig.example.h 为私有 WifiConfig.h，使 S3 加入 Z15 现有的受保护热点。交付源码不含热点密码；板上部署使用的含凭据固件保留在本机私有构建目录。

```powershell
python build.py --arduino-cli "你的 arduino-cli.exe 路径" --arduino-config "你的 arduino-cli.yaml 路径" --wifi-config "你的私有 WifiConfig.h 路径" --work-dir "源码目录之外的私有构建目录" --ble-library "Arduino-ESP32/3.3.11/libraries/BLE 的实际路径"
```

主机行为检查在 C++ 开发环境执行 `python run_tests.py --cxx cl`，或指定 g++/clang++。每次替换模块应核对 PendulumBleConfig.h 的实际地址及 FFE0/FFE1 服务。

2026-10-19 实测发现 MTU 请求返回 EALREADY（已有交换请求），Arduino-ESP32 3.3.11 将它当成连接失败，同时留下底层连接句柄，导致后续重试一直被拒。build.py 用 ble_compat.py 检查已审阅的 BLEClient.cpp 摘要，在私有目录复制库后只处理这个返回码，保留其他错误与原安全流程；安装目录原库保持不变。修改摘要记录在私有 ble_compat_manifest.json。MSVC 开发环境执行 `python -m unittest discover -s tests -p test_ble_compat.py` 可检查 EALREADY、其他错误和正常等待三条分支。


## 启用与停止

倒立摆仍使用原 network/source/enable/start/stop/left/right 命令及眼控入口。启用先同步停止，再等待 STM32 回报停止、已连接且解锁；后续新动作才会下发。状态增加 `transport=ble`、`stm_linked` 和 `neutral_ready`，原 `bridge_link` 字段保留兼容。

蓝牙连接和 GATT 写入在独立任务中执行，主循环只交换最新输出。主循环输出过期 150ms 后下发无效停止帧；STM32 原 400ms 接收超时保留。收到新的 STM32 状态才更新反馈新鲜度，超过 1000ms 失效。断连、重连和 STM32 重新锁定都撤销旧会话；重启或恢复连接不自动启用倒立摆。网络来源及眼控显示租期仍由原实现管理。

## 当前验证

现场连接、双向透传、STM32 状态和烧录证据见 [验证记录](report/verification.md)。2026-10-19 已修复实际 MTU 请求冲突，完整链路的状态回传、中立确认、停止、禁用、重新启用、主动断开与心跳超时检查通过。修复版仅写原 app0（0x10000），设备端校验通过。测试结束恢复倒立摆原 emg 模式并禁用；机械启动、左右动作、平衡效果及冷启动仍待验收。见 [上电验收与回退](ACCEPTANCE.md)。

2026-10-21：射频重连修复已写入 S3 app0 并核对哈希。手端实际有效反馈、Z15 眼控链路单次启用与张开/闭合/再张开回执通过，用户确认正常闭合并重新张开。Nano、STM32 和倒立摆 BLE 实现未改动。启动区/分区表相同，NVS 中开合姿态记录相同；无线 PHY 自动校准记录有更新。详见当前展示包 report/commissioning_20261021。
