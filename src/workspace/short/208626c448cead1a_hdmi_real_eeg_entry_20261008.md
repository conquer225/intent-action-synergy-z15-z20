# 临时真实 EEG / HDMI 测试入口

范围：单次最多 600 秒的易失 ARM 覆盖；已有 eye_wifi.bit 显示；静音；无眼控初始化；实体轮椅输出始终禁用。结束先关闭显示并恢复 guardianloop_pynq.bit，再删除本次精确 /run 服务覆盖并重启正式采集。没有修改 /etc、模型、正式文件或启动镜像。

## 本次证据

- 正式进程 PID 30461 不变期间，malformed_bytes、sequence_gaps 增长并出现 MALFORMED_STREAM / PRIMARY_STREAM_RESET。异常帧、接收时间间断会清空校准窗口；没有证明 USB、无线或电极中的哪一项是底层原因。
- 临时三个 SSVEP 模块围绕经 SHA256 校验的正式 ARM 入口加载；复用原串口采集与 bounded tap，没有第二个 USB 读取者。板端 16 项隔离测试通过，真实 spawn 子进程 HTTP 预检通过；该预检不接串口、不加载 PL。
- 第一次显示启动缺少隔离目录的 wheelchair_ssvep.dry_run_bridge，失败证据保留；报告确认 DMA 关闭、缓冲释放、正式 PL 恢复。补齐的是已校验的虚拟方向依赖，不包含电机传输。
- 第二次显示会话 play-e14751d2 已进入实际视频和菜单。鉴权 HTTP force_stop 经真实进程确认 home / stop / force_stopped=true / stimulus_enabled=false / physical_output_enabled=false；这不等于已验证闪烁时停止或实际轮椅急停。
- 最新准备状态为 speed、reading=false、最低档 1、虚拟方向未启用、刺激未启动、硬件输出 false。
- 临时采集一段记录达到 86,000 包、格式错误 0、序号缺口 0、校准 15/15。期间仍有过期监测结果撤销事件，不能将这一段称为长期链路稳定性验收。

恢复计时器：gl-hdmi-live-20261008-9c94dcef-recover.timer，2026-10-08 13:31:36 UTC 到期。未自动开启可见闪烁。真实频率识别、休息撤销、实际闪烁时停止尚待用户主动短测。

本地证据目录：phone_video_upload/output/hdmi_live_20261008，特别是 spawn-preflight-retry.json、http-stop-receipt.json、ready-recheck.json。网页密钥不写入此文档。
