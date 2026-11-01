# 用户控制关闭的 HDMI / EEG 会话

用户明确要求重新开启，并取消固定到期关闭。范围是当前上电会话；没有变更开机镜像或将候选模块宣布为已正式验收。物理轮椅输出始终禁用。

## 已部署

- Z15：隔离目录 /home/xilinx/gl-hdmi-live-20261008-ea117349。
- ARM：围绕校验后的原正式采集入口，复用原串口采集及 bounded tap；仅加载既有三个 HDMI SSVEP 候选模块。模型、固定八通道和质量门不变。
- PL：既有 eye_wifi.bit / eye_wifi.hwh；用户要求关闭后恢复 guardianloop_pynq.bit，再恢复原 ARM 入口。
- 网页：手机热点地址 192.168.43.6，端口 9119，沿用用户密钥。密钥不写入文档。
- 网页、硬件显示进程与独立异常守护的 RuntimeMaxUSec 均为 infinity，本轮 0 个到期计时器。
- 播放循环的截止时间为 None。诊断历史限制在最近 4096 个样本；历史截断时不声称全程 16fps 验收通过。
- 独立守护不按会话年龄关闭：正常心跳即使运行 24 小时也不会触发恢复。只处理显示进程退出、报告异常或心跳过期；复用原有验证所有权、先停 DMA / 恢复 PL 再处理进程的恢复流程。
- 15 秒无新可信方向返回主页、单轮最多 30 秒闪烁、扫描心跳及 EEG 过期撤销保留；这些不等于关闭网页会话。
- 没有自动启动可见闪烁；由用户勾选确认后开始。无声音、无眼控自动初始化、无实体轮椅动作。

## 验证

本地与板端各 21 项 Python 检查通过，手机 JS 检查通过；真实 spawn HDMI 接口预检通过，不打开串口或加载 PL。实际显示会话 play-fe7a406c 已进入视频界面，系统输出 physical_output_enabled=false / stimulus_enabled=false。独立守护、网页和显示均 active。

重启后的实际采集记录曾达到 36,000 包、格式错误 0、序号缺口 0、校准 15/15、质量 good。该短段不证明长期稳定性或 SSVEP 准确率。

本地证据目录：phone_video_upload/output/hdmi_live_user_controlled_20261008。重要文件：software-tests.json、spawn-preflight-retry.json、opened-status.json、persistent-units.json、persistent-timers.json。

## 关闭

本机执行 run_hdmi_live.py restore --keep-open 可停止本会话的守护，先恢复显示 / PL，再关闭网页，移除属于本会话的精确 /run 服务覆盖并恢复原采集。不得用其他历史 state.json 处理本会话。保留隔离目录及证据；没有删除用户媒体。
