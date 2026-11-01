# PC 控制与本机演练

这些工具只依赖 Python 标准库。建议使用 Python 3.10 或更新版本；Windows 官方 Python 安装包通常包含 Tkinter。工具不下载依赖、不烧录固件。TCP 控制与 USB 标定是两个入口。

## 本机演练

双击 `launch_simulation.bat`，打开标有“本机模拟”的窗口，然后点“连接”。也可以在项目目录运行：

```powershell
py -3 tools/pc_gui.py --simulate
py -3 tools/pc_client.py --simulate
```

命令行连接后输入：

```text
status
hand mode network
hand enable
hand close
hand open
pendulum mode network
pendulum enable
pendulum start
pendulum stop
estop
quit
```

模拟器固定绑定 `127.0.0.1`，内置演练使用随机空闲端口。它提供合成的五路压力、五路 PWM、六路角度和六路 ADC；标定、RF、桥接就绪标志是测试夹具。它可以检查协议、模式、来源占用、心跳和断线行为。倒立摆动力学、传感器误差、射频丢包、电机限位和硬件保护必须在实物上验证。

需要单独启动模拟器时运行以下两条命令。第二条命令在另一个终端执行：

```powershell
py -3 tools/mock_server.py --port 9000
py -3 tools/pc_gui.py --host 127.0.0.1
```

## 连接 ESP32

从 ESP32 的 USB 状态输出取得当前 IP，确认电脑接入相同 Wi-Fi，再运行：

```powershell
py -3 tools/pc_gui.py --host <ESP32的IP>
py -3 tools/pc_client.py --host <ESP32的IP> --source pc
```

窗口和命令行都不会自动切换模式、启用设备或恢复动作。选择 `network` 模式后，需要单独发送 `enable`。同一来源只能连接一个客户端；不要让命令行和窗口同时使用 `pc`。关闭窗口、退出命令行或发生调用异常时，工具尽力发送 `all estop`，再关闭连接。这个有意发送的全局急停会停用本地模式中的设备；意外断线时，固件只停止该来源绑定的网络模式设备。

首次接实物先通过 USB 完成标定，并保存张开、闭合姿态。查看 `pot_calibrated`、`poses_ready`、`pressure_calibrated`、RF 和执行器就绪状态，再启用灵巧手。界面中的目标角度初始为空，需要填写六个 0–180 的整数才可发送。数值范围只是协议校验；实物各关节的机械范围由固件配置和已完成的标定决定。

急停按钮发送 `all estop`，不等待普通界面请求结束。没有 TCP 连接时，按钮不能向实物送达指令。断线后界面会保留上次反馈并标明未连接；这些数值不代表当前硬件状态。

## 脚本与眼控、脑控入口

`--source eye` 和 `--source brain` 为外部控制程序标记来源。工具没有眼动或脑电分类器，外部程序需要把识别结果映射到本协议的动作。

脚本文件是 JSON 数组。工具先校验整个文件，再打开连接；任何命令被拒绝或连接异常都会结束脚本，并关闭会话。以下内容可保存为 `my_actions.json`，先用于本机演练：

```json
[
  {"device":"hand","action":"mode","mode":"network"},
  {"device":"hand","action":"enable"},
  {"device":"hand","action":"close"},
  {"wait_ms":600},
  {"device":"hand","action":"open"},
  {"device":"all","action":"estop"}
]
```

```powershell
py -3 tools/pc_client.py --simulate --script my_actions.json
```

`wait_ms` 是 PC 侧等待，不发送到 ESP32；等待期间客户端继续收 ACK 和心跳。脚本不应包含 `v`、`seq`、`source`、`hello` 或 `heartbeat`，这些字段由客户端管理。显式指定 `--host` 才会连接实物；`--simulate` 禁止与 `--host` 组合。

外部识别程序可以导入 `ControlClient`。把它放在 `with` 作用域里；循环结束或异常会触发关闭。连接丢失抛出 `ClientError`，由上层明确决定何时重新连接。下面的入口只取得状态，不会启用或驱动设备：

```python
import sys
sys.path.insert(0, "tools")
from pc_client import ControlClient

with ControlClient("<ESP32的IP>", source="eye") as client:
    reply = client.send("all", "status")
    print(reply)
    # 根据已验证的识别结果，显式选择模式、启用并发送动作。
```

所有命令都有返回 ACK；调用方应检查 `reply["ok"]`。`ok:false` 是固件的业务拒绝，不自动重试。心跳每 100 ms 发送一次，连续等待某个 ACK 超过 350 ms 会关闭连接。后台线程为守护线程，不能维持已退出进程的租约。收到的主动遥测保存在 `latest_status`，事件队列 `events` 最多保留 256 项。

## 检查工具

在项目根目录运行：

```powershell
py -3 -m unittest discover -s tests -p test_pc_client.py -v
```

测试只创建本机 TCP 服务器，检查长连接空闲心跳、递增序号、帧拆分与合并、主动遥测、心跳 ACK 超时、重复来源拒绝、跨来源控制拒绝、异常退出、断线后无重放和手动重连。它不需要 Arduino、STM32、串口或 Tk 图形窗口。

完整协议见 [docs/network_api.md](../docs/network_api.md)。
