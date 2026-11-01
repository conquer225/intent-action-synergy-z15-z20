# GuardianLoop 正式版冻结包

发布版本：`guardianloop-fixed-cap-20261001`。本包在156秒台架多任务预测负载、PC数值参考和故障撤销检查通过后封存；不是训练数据集、全卡镜像或准确率证明。没有新增PL部署，没有修改ARM正式程序或启动镜像。

## 包内内容

- `SOURCE_AND_BOARD_RECOVERY.zip`：之前核验过的完整工程/恢复交接包，包含当前正式FPGA源码、配套bit/HWH、板上ARM程序/模型、startup/cyton/web/AP/DHCP服务和板级配置。先解压这个内层包，再按其README核对或恢复。候选目录只是研究参考，不能与正式bit/HWH混用。
- `FROZEN_RELEASE.json`：25个安装文件、实际板端配置/启动文件的精确哈希、冻结范围、boot ID。
- `acceptance/`：完整验收数据、报告，以及从板上下载的 `installed_runtime/`；后者用于本地数值对照，不是新安装器。
- `bench_input/`：本次非佩戴台架回放样本和原来源清单，不能作为真实情绪/疲劳标签数据。
- `reproduce/`：本次数值审计和验收脚本。连接/部署辅助模块位于内层工程 `projects/codex_project/eeg_apps_z15/`；重跑时将新版脚本放回对应工程目录，不要在任意目录直接执行板端操作。
- `SHA256SUMS.txt` 与外部 `.zip.sha256`：完整性核验。

## 当前分工

CH1–CH8固定为 `F3,F4,C3,C4,T7,T8,O1,O2`。连续滤波、SQI、GAMEEMO情绪六通道、疲劳四通道、SEED八通道、SSVEP O1/O2推理均在ARM。PL加载的是正式历史DE/HGB设计，当前固定帽位模型不调用这些旧核。候选滤波/矩阵核未正式上线。

## 只读核对

```sh
cat /run/guardianloop-startup/status.json
cat /proc/sys/kernel/random/boot_id
systemctl is-enabled guardianloop-startup guardianloop-cyton guardianloop-web guardianloop-ap guardianloop-dhcp
systemctl is-active guardianloop-startup guardianloop-web
curl -fsS http://127.0.0.1:9102/api/status
```

startup的boot ID必须匹配当前启动。Cyton关闭时无新鲜EEG为正常情况，不能拿 `active` 代替包流正常。不要拿本包旧状态文件覆盖 `/run/`，也不要用候选bit替换正式bit。

电脑工程保留时可只读运行：

```powershell
python D:\ican\codex_project\eeg_apps_z15\deploy_startup.py verify
python D:\ican\codex_project\eeg_apps_z15\check_frozen_release.py --output D:\ican\codex_project\eeg_apps_z15\output\final_multitask_acceptance_20261001_1549
```

## 恢复边界

优先使用已工作的克隆卡。内层 `board_snapshot/rootfs/` 保留原Linux路径布局，但不得整体覆盖到任意系统根目录；先备份目标卡、对照内核与版本，按内层README逐项恢复。运行文件更新必须同步发布清单。

原电脑的部署撤销命令为 `python D:\ican\codex_project\eeg_apps_z15\deploy_startup.py rollback`，它会变更/重启服务、撤销此次新增startup配置，而且拒绝覆盖后续改过的文件。**日常复核不要执行rollback。** 内层源码/配置快照提供文件级恢复，不等于已验证全SD镜像恢复；完整损坏卡的系统恢复仍需要正常克隆卡。

## 还差什么

本轮软件部署收尾已完成。当前识别展示主线剩一次合并现场佩戴验收：真实输入、质量与正常预测，以及10 Hz／12 Hz／休息的有提示SSVEP闭环；不要求使用者模拟情绪或猜测疲劳标签。若要求控制ESP32或执行器，再加一个明确低风险动作的外设闭环阶段。目前外设控制禁用、运动想象未在本次交付，SSVEP光学频率仍未实测。

本包含热点密钥、网络配置及部分开发连接参数，**仅发送可信队友，不要公开上传**。查看 `acceptance/RESULTS.md` 了解有限时间负载、故障恢复和准确率证据边界。
