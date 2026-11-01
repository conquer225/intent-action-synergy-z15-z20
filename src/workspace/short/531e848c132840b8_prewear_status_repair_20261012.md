# 2026-10-12：停流显示与佩戴前准备提示修复

## 已确认的原因

用户报告 Cyton 已关闭，网页的“输入包年龄／快照年龄”仍增长到约
68,431 秒。板端采集进程处于 WAITING_FOR_CYTON，本进程 packets_seen=0；
USB 接收器存在不代表采集板正在发送。TelemetryResponseCache 用现在时间
减去最后一次快照发布时间，再加输入在快照发布时的年龄，因此旧文件
不变时年龄仍会增长。它不是持续收到新包，也不是一次计算花了这些时间。

另一项只读检查发现，原 HDMI 会话 play-52f4b09f 已失败退出，报告错误
为 Runtime guard heartbeat expired，original_restored、buffers_released、
display_halted 均为 true。报告保留 3,122 次守卫检查，已完成检查的最大
耗时约 457.1 ms，最后十次约 111–190 ms。这些已完成检查不足以解释
最后为何出现四秒心跳缺口，不能据此认定为模型运算或无线硬件故障。

## 本轮已修复并上线

- 实时数据过期后，主网页显示“无新鲜输入 · 旧快照已停用”，不再显示
  持续增长的大数字。采样率和计算耗时不沿用旧值；旧包数标明历史快照。
  API 中年龄仍保留为诊断信息，三秒过期判断没有放宽。
- API 撤销旧预测时保留明确的 WAITING_FOR_CYTON 等中断原因，不再把
  已知等待状态一律覆盖成 STALE_EEG。情绪／疲劳输出仍失效，校准保留
  信息不变。新的及时快照到达后，原有实时数值显示自动恢复。
- 主网页新增只读佩戴前提示：接收器、采集、及时输入、HDMI 软件会话。
  手机版设备信息也显示 HDMI 未就绪。没有新轮询接口或自动启动刺激。
  HDMI ready 仅表示软件快照在三秒内更新，不证明光学时序或物理屏幕正常。
- 状态时间为未来、非有限数或非法对象时，不再当作当前有效输入。
  Telemetry 缓存遇到时钟回拨也按过期处理，不伪造零秒新鲜度。

修改复用既有缓存、状态读取和恢复安装器。未改滤波、模型算术、质量
门槛、串口驱动、队列容量、SSVEP 判决、RuntimeWatch 四秒保护或 PL。

## 验证和部署

修改前相关 Python 测试 12 项：11 通过、1 个平台 fixture 跳过，Node
虚拟 DOM 检查通过。修改后的本地 Python 34 项：29 通过、5 个 Linux
fixture 跳过；Node 的停流、恢复、连接失败、轮询不重叠等检查通过。
第一次新增 Node 用例未恢复后续用例的输入 fixture，出现一项失败；
修复测试隔离后通过，没有降低断言。板端 Python 3.8 六组共 39 项全部
通过，17.942 秒，没有读取真实串口、加载 PL 或产生闪烁。

沿用精确九目标安装计划，其中两个计算源文件指纹不变；实际源码修改
仅 guardianloop_web.py 与 mobile.js。其余变化为发布清单、守卫的准入
清单指纹、启动报告、HDMI wrapper 状态和 boot-pins。独立 150 秒回退
保护保留；安装、在线检查和提交连续执行。采集和两个网页服务短暂
重启，不启动显示、不加载 bit、不改 SD 开机镜像。

新发布：`guardianloop-stream-status-repair-20261012`。
清单 SHA256：
`04c24472f64e9edd36c0a73cb5117f43cd69193798ea78007208a60d92d9e45d`。
正式 57 文件与 79 boot-pins 全部匹配，安装状态 committed，回退 timer
inactive。服务采集 PID 19872、主网页 PID 19876、媒体网页 PID 19881，
均 active。本轮明确重启过服务，不能据 NRestarts=0 说成从未重启。

同次开机 ID 仍为 `0e44bc51-655b-4974-b982-d6689fa20948`，校准 15/15，
calibration_retained=true。校准与 wear 文件 SHA 分别保持：

```
639c5b58c7e34d6b040f759f7794fa4a6ec93acfb943c0284391245be1333c49
980c25f97e458583211c3b46a9fc97c422d95f28d2a8c9cf96fe5503ff99a412
```

最终状态是 WAITING_FOR_CYTON、valid=false，情绪也无有效分类。
HDMI 仍明确为 error/ready=false，没有自动重启。PL 元数据为正式
`/home/xilinx/jupyter_notebooks/guardianloop_pynq/guardianloop_pynq.bit`，
这是旧显示退出时恢复的状态，不是本轮重新烧录的结果。

证据：`phone_video_upload/output/stream_status_repair_20261012/`。
含 before-health、stage、linux-tests、deployment-plan、install-and-live-check、
final-health、post-install-observation、rollback-timer。板端备份保留在
`/home/xilinx/gl-calibration-install-20261011-l1NbvH/backup`；目录沿用
既有安装器前缀，发布日期为 10 月 12 日。不含新采集的原始脑电。
备份中有私有校准状态，不应放进公开工程包。

## 仍未通过的项目及下次顺序

1. 先不开帽、不闪烁，在 Cyton PC 模式开机后完成完整 40 秒纯收包检查。
   先前测试只完成约 33.38 秒，存在坏字节和序号缺口，不能算稳定性通过。
   接收器 USB 供电／无线链路／驱动的具体原因仍未确定。
2. HDMI 守卫超时需单独定位，保留原保护。进一步出画测试涉及重新加载
   eye_wifi.bit，须取得本轮明确授权；退出仍恢复 guardianloop_pynq.bit。
   没有在本轮把“四秒保护”改长或删除来宣称已解决。
   后续用户已授权并完成一次 30 秒静态诊断：无错误、正式 PL 已恢复，
   长时超时尚未复现。见 [HDMI_GUARD_DIAGNOSTIC_20261012.md](HDMI_GUARD_DIAGNOSTIC_20261012.md)。
3. 两项准备检查通过后再佩戴，检查质量、基线和新鲜窗口，再做四频＋
   中心休息；实体轮椅继续禁用，先验识别与强制停止。

同次开机、同次佩戴的断流恢复保留校准，不等于换人、重新佩戴或改变
电极位置后仍可盲用旧基线。新佩戴须走已有明确确认入口，不能靠更改
15/15 显示来省略。Unified PL 工程融合仍在主线，显示版 Vivado 源码
缺失；本轮没有宣称它已经完成。
