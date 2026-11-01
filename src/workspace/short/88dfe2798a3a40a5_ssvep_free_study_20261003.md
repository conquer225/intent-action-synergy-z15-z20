# 四角 SSVEP：原始录制关联与独立采集流程

2026-10-03 已接入正式 ARM 网页。完成的是采集、追踪和安全拒绝流程，
不是新模型训练或识别准确率提升。本轮 Cyton 关机，不要求佩戴，没有启动真实屏幕闪烁或真人录制。

## 当前部署

- 当前发布：`guardianloop-fixed8-ssvep-study-20261003`，上一发布为 `guardianloop-fixed8-ssvep-wait-20261003`。
- 网页：`http://192.168.2.99:9102/ssvep-free`；主页面、有提示 SSVEP 和 MI 入口保持。
- 板端目录：`/home/xilinx/jupyter_notebooks/guardianloop_pynq`。
- 物理八通道仍为 `F3,F4,C3,C4,T7,T8,O1,O2`，SSVEP 仍仅解码 O1/O2。
- 新增 `ssvep_study.py`；修改 `ssvep_free.py`、`ssvep_free.html`、`ssvep_cue_runtime.py`、
  `ssvep_recording.py`、`cyton_trial_recorder.py` 和发布清单。
- 仅重启 ARM 采集和网页服务。模型、MI root 配置、PL bit/hwh、systemd 服务文件、设备树和启动镜像未改。
  未重启板卡，未启用物理控制，未晋升隔离 PL 滤波共存候选。
- 46 个发布文件校验通过；部署账本为
  `D:\ican\codex_project\eeg_apps_z15\output\ssvep_free_study_20261003\deployment.json`，`phase=verified`。

## 已实现

### 原始录制先于刺激

自由选择页新增“同步保存八通道原始脑电”。勾选后由板端建立本次独有记录，
至少收到 250 个样本及 8000 字节原始计数后才就绪，再允许浏览器开始刺激。
准备期间不闪烁。失败、取消及迟到 ACK 均走关闭流程；不会接管另一页的外部记录。
有提示页和自由页的会话、待关闭原始录制互斥。

每个自由事件含 `raw_recording_id` 与 `board_boot_id`，便于与五类原始二进制文件和元数据关联。
原始记录丢失/更换时撤销要求同步录制的自由会话结果。
停止、页面隐藏、取消主动确认及异常时撤销刺激和选择结果，并关闭本次拥有的记录。
板端保留 45 秒录制上限，避免浏览器消失后无限录制。

普通自由演示仍可不勾选录制；它没有预定注视标签，不可当作带标签准确率实验。
无数据、坏质量或歧义不是“休息”输出；当前休息拒绝仍未完成真人验证。

### 事先固定的采集计划

勾选“四角独立采集”后，可以主动建立计划。建立计划只保存计划文件，
不启动原始录制、解码会话或闪烁。

- 共 20 段，前 10 段为校准采集，后 10 段为独立确认。
- 每阶段 `8、10、12、14 Hz、中心休息` 各两次；分别在两轮中随机排序，保存种子、顺序和摘要。
- 两阶段不同 `block_id`；每段新建原始记录，不能共用记录或拆重叠窗口充当独立确认。
- 每段主动点击开始，约 10 秒后停止，不自动连播。可以在段间休息。
- 休息条件是“看中心静止区，四角仍同时闪烁”，不是有提示页的“全屏不闪烁”。
- 请求注视只保存在计划/原始元数据及指导文字中，不传入自由解码器。
  接口仍拒绝 `target_hz`、`selected_hz`、`result` 等期望答案字段。
- 失败或提前取消段仍保留并占用原先计划位置，不静默挑选成功段重新测试。
- 冻结现有解码代码、滤波资产及门控版本摘要，避免运行中改变算法后混入确认记录。

计划按记录/阶段隔离是同一次佩戴的独立记录设计，不是跨人验证。
请求注视没有眼动仪确认，标签是行为指令而非已验证的注视真值。
浏览器回调/服务接收时刻不等于光学 onset 或 ADC 时间戳。

当前门限仍为 CCA ≥0.55、领先差 ≥0.10，连续一致覆盖两段不重叠 2 秒窗口。
CCA 分数不是概率。没有偷偷放宽门限、把未识别改成休息、交换频率答案或拟合新阈值。
`thresholds_fitted=false`、`control_enabled=false`、`production_eligible=false` 保持。

### 离线审计工具

`D:\ican\codex_project\pynq_guardianloop\audit_ssvep_study.py` 只读检查：

- 冻结计划摘要、固定通道、标签顺序、两阶段均衡与原始记录不重复；
- 元数据/协议关联、五类文件长度、接收时间和连续主流索引、包序号异常标记；
- 原始记录与事件的 boot/会话 ID，以及刺激开始至结束的原始覆盖；
- 保留缺失、取消和不完整段；列出拒绝原因及确认休息段中出现稳定频率的情况。

工具不训练、不改板卡、不生成真人准确率结论；输出使用新文件名，拒绝覆盖旧审计。
原始数据取回后可用以下形式运行，`<...>` 必须替换为真实文件路径：

```powershell
& 'D:\ican\codex_project\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 'D:\ican\codex_project\pynq_guardianloop\audit_ssvep_study.py' --study '<本地计划JSON>' --recordings '<本地recordings目录>' --events '<本地ssvep_free_events.jsonl>' --output '<新的审计JSON>'
```

板端计划在 `/home/xilinx/jupyter_notebooks/guardianloop_pynq/ssvep_studies/<study_id>.json`，
原始记录在同级 `recordings/<raw_recording_id>/`，事件在同级 `ssvep_free_events.jsonl`。
板端日历时钟仍不可信，关联以 boot ID 和单调时间为准。

## 验证结果与限制

证据目录：`D:\ican\codex_project\eeg_apps_z15\output\ssvep_free_study_20261003`。

- `pc_tests.log`：126 项，11 项 Linux 专用跳过，其余通过，40.926 秒。
- `arm_tests.log`：126 项全部通过，69.074 秒；在隔离候选目录和 RAM 临时目录运行。
- `browser_tests.log`：虚拟 DOM/帧调度通过，包括录制先就绪再启动、失败不启动 RAF、
  建计划不闪烁、独立计划不发送期望频率。不是用户屏幕光学测试。
- 合成负对照将计划期望与脑电候选设置为不同频率，输出仍由脑电候选决定，不用计划答案。
  另覆盖短首批 ACK、取消/迟到 ACK、两页互斥、丢失原始关联撤销、失败段保留、协议重标拒绝。
- 两次 PC 失败日志保留为 `pc_tests-attempt-*.log`。新用例的假时钟/新鲜 EEG 夹具不正确，
  修正夹具后重跑全部测试，未放宽生产门控。
- `postflight.json`：四入口在原 3 秒请求限制下通过；46 文件清单、模型及保护文件哈希通过。
  首次复核遇到 `KeyError: candidate_model`，随后只读 MI 状态正常且完整重跑通过。
  `verification_attempt_1.json` 保留失败。未以最终通过掩盖启动阶段短暂未就绪问题，
  本轮没有修复部署复核器对此短暂状态的竞态。
- `no_data_soak.json`：21 次采样，79.063 秒，同一 boot。
  采集 PID 31239、网页 PID 31240 始终未变，两服务 NRestarts 始终为 0，active/running。
  有提示/自由 SSVEP 始终 `no_data/waiting_for_cyton`，没有接受/旧结果；MI 同样无结果或物理控制。
- `no_data_refusal.json`：无数据时原始录制及刺激启动均返回 400；命令文件哈希、
  原始记录目录和计划目录未改变。会话/录制 idle，计划 not_created，result=null。
  验收没有为了测试而建立一个正式计划或制造真人记录。

上线停止旧采集进程时，既有 MI 进程通信产生 BrokenPipe 关闭日志；新进程的模型已就绪，
等待段无重启。本轮没有修改该既有关闭路径，也不把它误写成新版连续采集故障。

尚未验证：新的四角注视/中心休息表现，个体阈值拟合后的独立确认表现，
8/14 Hz 真佩戴识别、真实屏幕光学时序、Cyton 实物晚开机恢复和新版本冷启动。
“原始采集完成”标记只作初筛，必须进一步离线审计，不能替代完整性核验。
服务重启不自动续接旧计划；文件保留，但内存计划清空。不要将重启后的新计划与旧计划合并
冒充一次连续确认；中断计划按实际完成情况单独报告。

## 复核和回退

已有候选执行顺序 `prepare → test → install → verify → soak` 本轮全部完成。
若候选运行源码改变，`refresh` 会撤销已测试状态，必须重新测试。
不要再运行旧 profile 的 verify，把旧清单当成当前正式发布。

```powershell
& 'D:\ican\codex_project\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 -c "import sys,runpy;sys.path.append(r'D:\Users\lenovo\anaconda3\Lib\site-packages');sys.path.insert(0,r'D:\ican\codex_project\eeg_apps_z15');sys.argv=['deploy_ssvep_free.py','verify','--profile','free-study'];runpy.run_path(r'D:\ican\codex_project\eeg_apps_z15\deploy_ssvep_free.py',run_name='__main__')"
```

板端交易/回退包：`/home/xilinx/ssvep-free-AURUHm`。需要回到 wait 版本时，先结束所有真人试次/录制，再执行：

```bash
sudo /usr/local/share/pynq-venv/bin/python3 /home/xilinx/ssvep-free-AURUHm/mi_rms_bundle.py rollback --bundle /home/xilinx/ssvep-free-AURUHm
```

回退仅针对本次 ARM 文件和发布清单；新 `ssvep_study.py` 可恢复地移入 withdrawn 目录。
受保护文件若被他人改写，哈希守卫会拒绝，不应强行覆盖。回退不删除真人原始记录。

本地恢复包：
`D:\ican\codex_project\eeg_apps_z15\output\ssvep_free_study_20261003\guardianloop_ssvep_study_arm_recovery_20261003.zip`。
包包含运行快照、新旧交易文件、测试与部署证据、说明和离线审计工具，排除缓存、SSH 凭据及真人 EEG。
它不是完整 SD 镜像或可重建 Vivado 硬件工程；保存的正式 bit/hwh 不会被 ARM 回退工具烧写。
ZIP 的逐条校验和总 SHA256 位于同目录 `recovery_zip_verification.json`、`.zip.sha256`。

## 下一步

软件准备已完成，无需现在打开 Cyton 或佩戴。以后方便佩戴时，可以一次完成 20 段短试次，
中间可暂停休息，不需要猜自己的情绪/疲劳。先审计原始数据和失败段，
只用校准记录确定候选门限/方案并冻结，再对确认记录做一次独立评估；
不能根据确认结果反复选择阈值。分别报告目标识别、拒绝率、中心休息误触发与决策时长，
结果不足则保留实验状态，不启用实体灵巧手。

EEG 实验审计规则影响了本次实现：记录级分离、先冻结计划、失败段保留、标签隔离于解码器。
本次是工程落地证据，没有把合成测试、浏览器回调或短时无数据板测当作生理准确率证据。
