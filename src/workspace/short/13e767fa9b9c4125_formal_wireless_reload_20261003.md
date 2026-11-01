# 正式 ARM＋PL 无线重载记录

2026-10-03，用户明确授权重载当前正式 ARM＋正式 PL，不改 SD 启动镜像、
不更换隔离候选。网口断开，经串口确认 Z15 Linux 正常运行，使用无线网卡热点完成操作。

## 最终状态

- 正式发布仍为 `guardianloop-fixed8-ssvep-study-20261003`。
- 46 个运行文件及发布清单已重新复制，最终哈希与冻结恢复包一致。
- 正式 `guardianloop_pynq.bit/.hwh` 已通过启动自检重新加载，不是新生成的 bitstream。
  bit 文件头确认 `7z015clg485`，没有调用 Vivado/JTAG 或烧写 Flash。
- 实际 PL 读取标识：DE `44453031`、HGB `48473031`、模型 `50537911`。
- 过滤/质量、情绪、疲劳、SEED、SSVEP 和 MI 的 ARM 构造自检通过。
  MI 仍为 shared-RMS 原模型，个人头和物理控制关闭；本次未训练或修改任何模型。
- 采集服务 PID 2815、网页 PID 2816，最终 active/running、NRestarts=0，短时复核保持稳定。
- `systemctl daemon-reload` 后两个服务 `NeedDaemonReload=no`；服务配置内容哈希未改。
- boot ID 始终为 `365d9217-edca-44d6-9266-83963abb1186`，与 COM14 串口读取一致。
  未重启板卡；启动镜像、设备树、MI 配置及受保护文件哈希一致。
- 未发起屏幕闪烁、真人录制或新的佩戴测试。无数据时保持等待，不能将此当成识别准确率验证。

## 无线连接

板卡：`GuardianLoop-Z15`，地址 `192.168.50.1`。电脑使用已保存的 Wi-Fi 配置，
每次切换均确认实际 SSID 和 `192.168.50.*` 地址后才访问板卡。
操作期间临时切换无线网络，完成后恢复电脑原有 `JLU.WIFI`，以维持互联网和对话。
用户查看无线网页时仍需连接 `GuardianLoop-Z15`，打开 `http://192.168.50.1:9102/`。

电脑在热点连接状态下对四个入口执行直接 HTTP 验收，均在原 3 秒限制内成功，
响应长度与板端对应页面一致：

- `/`：34,576 字节，命令耗时 0.078 秒。
- `/mi-cued`：11,230 字节，0.062 秒。
- `/ssvep-cued`：13,569 字节，0.094 秒。
- `/ssvep-free`：17,310 字节，0.063 秒。

耗时包含 curl 进程开销，不是模型推理耗时、刺激延迟或光学同步测量。

## 保留的失败与恢复

首次重载已通过 PL/模型自检，但后续 Python 网页请求超时，触发原应用恢复。
恢复副本与本次正式包原本就相同；保护流程重新复制原文件并重新加载正式 PL，服务恢复成功。
没有退回更旧的功能版本或改变模型。

第二次 Python 请求复核也超时；与此同时，串口调用 curl 直接访问四页均正常，
约 5–16 毫秒完成。最后使用同样 3 秒限制、禁用 HTTP 代理的 curl 完成板端及电脑无线复核，
全部通过。未放宽限制；Python 请求与直接访问的差异根因尚未进一步定位，
不能宣称该验证器问题已经修复。没有为这一差异继续反复烧写应用或更换模型。

本地证据：`D:\ican\codex_project\eeg_apps_z15\output\formal_wireless_reload_20261003_211426`。

- `preflight.json`：写入前发布、通道、boot、服务与无活动试次检查。
- `expected.json`：冻结应用/模型/PL/配置/启动文件哈希。
- `result.json`、`run.log`：首次超时和原应用恢复；首次 `passed=false` 保留。
- `verification.json`：最终 PL/ARM/哈希/四网页及短时稳定复核 `passed=true`，显式保留首次失败字段。
- `wireless_http.json`：电脑直接通过 `192.168.50.1` 访问四页面全部通过。
- `state.json`：最终 `verified_after_identical_recovery`。

## 文件及恢复边界

冻结来源：`D:\ican\codex_project\eeg_apps_z15\output\ssvep_free_study_20261003\package\runtime`。
板端阶段包：`/home/xilinx/formal-reload-Pckp4b`。
写入前的应用备份：`/home/xilinx/formal-reload-Pckp4b/previous`。
原始 EEG、采集计划和旧恢复包均未删除；本次阶段包也保留。

执行工具：`eeg_apps_z15/reload_formal_wireless.py`、`reload_formal_board.py`、
`verify_formal_reload_board.py`。共享 SSH helper 新增可选 host，默认有线地址不变，
没有修改或输出保存的身份凭据。重载需重新获取串口 boot ID 并建立新阶段，不能复用旧操作账本
盲目再次启动；若受保护文件出现他人修改、候选 DMA 驱动存在或试次/录制进行中，工具拒绝重载。

现有正式 PL 有 DE/HGB 等模块，但当前固定帽位主线的模型/处理路径仍在 ARM。
重载 PL 并不表示隔离滤波共存候选已上线，也不表示本次新增了 FPGA 加速或真人准确率证据。
