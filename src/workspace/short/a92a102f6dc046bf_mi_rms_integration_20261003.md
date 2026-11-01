# 2026-10-03 固定八通道 MI 虚拟控制接入

用户决定沿用刚试用的基础共享 RMS EEGNet；这项决定是虚拟控制试用接受，不是新增准确率证明。

## 已确认

- 正式入口为 `http://192.168.2.99:9102/mi-cued`；原 `9104/mi-cued` 直连入口保留。
- 固定八位置为 `F3,F4,C3,C4,T7,T8,O1,O2`，没有改帽位、增益、滤波、质量门限或标签映射。
- 模型 `experimental_rms_eegnet.npz` 的 SHA-256 为 `363daf3b68da6e80495319052447ec83e06b9e3e327a1bd0ff9e6023a5b54221`；个人适配头关闭。
- MI 推理与采集适配在 Z15 ARM，使用同一 USB 读包器的独立分发接口，不另开串口。
- 程序安装到 `/home/xilinx/jupyter_notebooks/guardianloop_pynq`；root 配置 `/etc/default/guardianloop-mi.json` 为 `{"enabled": true}`。
- `guardianloop-startup.service`、`guardianloop-cyton.service`、`guardianloop-web.service` 均保留开机启用。采集和网页已重启，startup oneshot 没有重跑。
- 虚拟动作仍需主动勾选，一次提示最多一次动作；真实外设输出永远关闭。
- 模型仍标注 `experimental_unpromoted`、`production_eligible=false`，没有把软件接入等同于研究晋升。
- PC／ARM 各 82 项单元测试通过；24 个保存窗口分类相同，ARM 与记录 logits 最大绝对差 `3.0531133177191805e-16`。
- Linux 模拟包流与参考模型 logits 完全一致，单次虚拟动作及停止撤销通过；模拟数据明确标记回放。
- 正式文件与服务检查通过，网页显示输入 ready、质量合格、虚拟控制未勾选。本次 PL、bit/HWH、设备树、内核模块、启动镜像和 boot ID 未改变。

## 未验证或不在本次范围

- 没有实际冷启动验收，也没有新增佩戴准确率、跨人准确率或整段原始脑电连续滤波重建结论。
- 没有接入物理灵巧手；没有开放无提示的持续脑控或模型识别的休息第三类。
- 主网页的启动记录仍来自当前 boot 的旧发布版本，可显示 `arm_update_pending_boot`；保留真实启动记录，不伪造冷启动成功。

## 证据及恢复

本地证据：`D:\ican\codex_project\eeg_apps_z15\output\mi_rms_integration_20261003`。
完整说明、程序、配置与恢复事务见该目录 `README.md` 和 `package/`。
板端备份：`/home/xilinx/mi-rms-integration-zvIG1b`。

需要撤销时运行：

```bash
sudo /usr/local/share/pynq-venv/bin/python3 /home/xilinx/mi-rms-integration-zvIG1b/mi_rms_bundle.py rollback --bundle /home/xilinx/mi-rms-integration-zvIG1b
```

恢复工具先核对哈希，只恢复本次明确目标；旧文件及移出的四个临时 systemd 覆盖均可恢复。
不要使用先前只撤销单个 `/run` 覆盖的旧脚本来撤销这次持久化接入。
恢复包排除个人 EEG 检查窗口、原始 EEG、个人交互事件、个人适配权重和连接凭据。
