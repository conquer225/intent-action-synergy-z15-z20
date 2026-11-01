# 上电验收与回退

2026-10-19 已完成完整蓝牙链路的状态回传、中立确认、停止、禁用、重新启用、主动断开和网络心跳超时检查。S3 COM27 已写入 MTU 冲突修复版，设备端摘要校验通过；STM32、Nano、Z15 运行文件和 FPGA 未重烧。测试结束恢复倒立摆原 emg 模式并禁用。机构启动、左右移动、平衡效果、蓝牙物理断连和冷启动继续按下列顺序验收。

## 开机与接线

按 README 的表格核对 DX-BT24 与 STM32：PA9 → 蓝牙 RXD、PA10 ← 蓝牙 TXD、双方及独立 3.3V 电源共地；蓝牙 3.3V 接独立 3.3V 正极，5V/STATE 悬空。C3/ESP8266 和 USB-TTL 不连接这对串口。STM32 与电机共用供电，上电前保持机构周边空出，暂不按启动或平衡键。

给 Z15、S3 正常供电，再给 STM32 和 DX-BT24 供电。S3/蓝牙之间没有额外数据线。Z15 用原 USB 网卡提供 GuardianLoop-Z15 热点。灵巧手保留原自动启动行为，初次验收倒立摆时先保持手端舵机电源关闭。

烧录后 S3 曾取得 `192.168.50.45`，重启后应重新核对，不能将此地址当作固定地址。可以从 S3 COM27 的 `stream status` 或 `link` 确认 Wi-Fi/桥接状态，含 IP 的状态行提供当前地址；USB 日志波特率 115200，蓝牙到 STM32 的业务串口仍为 9600。

## 先检查通信

电脑加入原 GuardianLoop-Z15 热点，在解压后的 pendulum_ble_update 目录运行：

```powershell
@'
import sys, json
sys.path.insert(0, 'pc_tools')
from pc_client import ControlClient
client = ControlClient('192.168.50.45')
try:
    client.connect()
    print(json.dumps(client.send('all', 'status'), ensure_ascii=False))
finally:
    client.close(safe_stop=False)
'@ | python -
```

这段脚本只连接、查询并关闭，不发送双端急停。原 pc_client.py 命令行在正常退出时会发送 all/estop，readonly_status.json 只限制脚本内的请求，不能覆盖该退出行为；只读检查使用上面的明确关闭方式。使用现场实际 S3 地址。检查回执中 `pendulum.transport` 是 `ble`，`bridge_link` 和 `stm_fresh` 都是 true，`enabled` 是 false。停止/未启用时 `blocked=1` 正常。若 bridge_link 为 false，核对蓝牙模块电源、是否被其他 BLE 连接占用、目标地址及是否使用修复版构建；若 bridge_link 为 true 而 stm_fresh 为 false，检查 PA9 → RXD、共地和 STM32 供电。

之前已分别实测电脑 ↔ DX-BT24 双向 60/60 帧，以及 STM32 → DX-BT24 → 电脑 125 帧状态。10 月 19 日的新 S3 中继已返回真实 STM32 状态，且中立、禁用、重连和 801ms 无心跳后的失效保护检查通过。短时结果见 report/verification.md，长时间负载另行验收。

## 再验收启用和停止

可以运行原 PC 面板：

```powershell
python pc_tools/pc_gui.py --host 192.168.50.45
```

先选倒立摆 network 模式，单独启用后只观察状态，暂不点平衡或左右动作。预期 STM32 保持 state=0，随后 stm_linked=1、blocked=0、neutral_ready=true。这是固件中立回执，实际机构状态还需观察。停用后应回到 enabled=false、blocked=1；断开电脑连接后也应停用，重连不会自动恢复启用。

上述检查通过后，现场确认机构状态，再分别验收左右短动作、停止、平衡启停及失联停止。没有完成这些实物检查前，不将机械动作标为通过。眼控详细页继续使用原协议；安装原 eye/eeg 更新时把 `--s3-host` 填为现场地址。当前用户要求其他功能照旧，本轮没有替换 Z15 的显示和采集运行文件。

## 回退

保留的 C3/ESP8266 原源码在 fallback_c3。回退要同时恢复 S3 的 C3 网络配置，并在断电时从 STM32 UART 移除蓝牙，再接回原 C3/ESP8266；禁止两路 TX 同时接 PA10。

本机已经核对并保存烧录前 S3 应用，SHA-256 为 `5f3b75ee5bda79effd83df3b0d2a39759a5112287d3edf6b5d31b7caffc6f1c5`，与板端 flash 摘要一致。私有备份路径是 `D:/fpga/z15_multimodal/local/commissioning_private/s3_before_ble_app_verified.bin`，启动区和 NVS 另存为同目录 `s3_before_ble_boot_nvs.bin`。它们不是完整芯片镜像。

需要回退时，先关闭倒立摆和舵机供电，仅保留 S3 独立供电与 COM27。用已安装的 esptool 将上述原应用写回 `0x10000` 并校验，不擦除 NVS、不改分区、不刷 merged.bin；原校准数据无需重建。本次没有改 bootloader 或分区表，正常回退也不需要重刷启动区。回退完成后再恢复原网桥接线、供电并只读核对状态。

私有部署程序包含本机网络配置，留在本机私有构建目录；完整工程 ZIP 分发源码、测试和说明，未导出热点口令或私有备份。
