# 四角自由选择 SSVEP 接入记录（2026-10-03）

正式入口：<http://192.168.2.99:9102/ssvep-free>，主页已有链接。
最初 ARM 发布标识：`guardianloop-fixed8-mi-ssvep-free-20261003`。
当前为 `guardianloop-fixed8-ssvep-usability-20261003`，见
[同步录制与具体拒绝原因修复](SSVEP_USABILITY_REPAIR_20261003.md)。
之前的输入调度修复见 [修复证据与恢复说明](SSVEP_READER_REPAIR_20261003.md)。

## 已实现并验证的软件行为

- 左上 8 Hz、右上 10 Hz、左下 12 Hz、右下 14 Hz；开始后启用的目标同时闪烁，中央与背景静止。另有 10/12 Hz 双目标选项。
- 默认停止、手动同意与开始，最长 30 秒；Esc、停止、隐藏页面或帧间隔超过 8 ms 都停止显示。
- 开始前要求 240 Hz 软件帧预检（235–245 Hz，p95 ≤ 6 ms，720 间隔中超过 6.25 ms 不多于 3 次）。8/10/12 Hz 使用 15/12/10 帧半周期，14 Hz 按时间相位切换，存在帧量化。
- 固定帽位 `F3,F4,C3,C4,T7,T8,O1,O2`，沿用 ARM O1/O2 连续滤波与 CCA。滤波系数、模型、质量门限、PL 和启动服务配置未改变。
- `/api/ssvep-free` 由采集进程中的 `SSVEPCueRuntime` 持有状态；网页只转发请求，GET 不累积 EEG 证据。自由选择不接收目标答案，也不用鼠标位置判断。
- CCA 最高分至少 0.55、领先分差至少 0.10，再要求连续同一候选覆盖两段不重叠 2 秒窗（相邻更新 50 样本，250 Hz）。首次至少等待刺激呈现后的完整 2.5 秒，再累计确认。
- 输入陈旧、硬质量失败、窗口中断、显示心跳消失均撤销旧结果。有提示与自由选择会话互斥。
- 仅频率候选展示，`control_enabled=false`。运动想象入口及用户选定的 shared-RMS 模型保留。

## 验证证据

目录：`D:/ican/codex_project/eeg_apps_z15/output/ssvep_free_20261003`。

- 电脑 Python 测试 48 项通过；Z15 Python 测试 48 项通过。
- JS 虚拟 DOM 检查通过：页面不自动闪烁、240/60 Hz 门控、四频率切换计数、隐藏/掉帧撤销、不发送目标答案。没有借此给用户实际播放闪烁。
- 合成 12 Hz EEG 经过真实 `SSVEPShadow` 连续处理和生产者回调，确认自由选择输出；独立单元输入分别覆盖四种选择。合成信号测试不等于人体识别准确率。
- `postflight.json`：四个网页入口可读取，MI 输入 ready，新自由选择状态 idle，42 个发布文件通过既有 `verify_files` 检查。
- 原模型、bit/HWH、根配置和服务文件以 SHA-256 保护；安装程序确认未重启板卡、未重新加载 PL。
- 页面证明：`four_corners_stopped.jpg`。

首次板端测试失败记录保存在 `arm_tests-attempt-1.log`。新增合成测试最初没有指定状态文件，默认临时路径与正式服务冲突；现已改成测试专属目录。遗留的、`updated_monotonic=100.0` 的空测试状态临时文件影响了服务重启，已核实后移到 `/home/xilinx/ssvep-free-uyAXXT/failed-test-shadow.tmp` 留证，采集服务已恢复。另两项旧接口测试受 SD 同步写延迟影响超时，单元测试临时文件移至 `/dev/shm` 后通过；真实接口超时和质量门限没有放宽。

首次发布后 HTTP 巡检出现过一次 3 秒超时。随后根页和 MI 页分别返回 HTTP 200（约 6/9 ms），完整巡检重跑通过。不能将本轮验证称为长期满负载或人体自由选择验收。

## 尚未验证的事项

- 历史阻塞（已做软件修复）：首次发布出现 `input_backlog`、输入延迟约 0.624–0.717 秒、`hard_bad=false`，MI 输入却 ready。SSVEP 当时在主推理队列中消费数据，持续陈旧输入阻止启动。
- 修复版已让 SSVEP 和 MI 从同一个串口读包器独立接收原始包；40 秒被动观察的生产者延迟中位数 33.55 ms、p95 70.01 ms，接口 37/40 次 ready。一次短积压触发拒绝与重新热身后恢复；这不是零停顿或长期稳定性证明，也不是人体自由选择准确率验收。0.5 秒门限及质量/CCA 阈值没有放宽。回放专用 SEED 异步候选未安装为实时服务。
- 工程阈值 0.55/0.10 没有用独立人体自由选择数据标定。它们不代表概率或置信度，未声称准确率提升。
- 看静止区域是用户表达“不想选择”的方式，系统不直接测量视线，也没有经过验证的休息分类器。周边闪烁、枕区自发节律等可能造成误选择。
- 8/14 Hz 的真实佩戴效果、四目标同时显示的识别正确率、拒绝率、延迟与休息误触发次数/分钟，均待独立试用评估。
- 浏览器帧时序不等于光学发光实测；目前没有光电传感器等实测条件。
- 没有连接真实灵巧手，没有执行新的冷启动/断电验收。

异步 SSVEP 的有目标/无目标判定可参考原始研究：
[idle-state detection](https://pubmed.ncbi.nlm.nih.gov/26246229/)、
[pseudo-key approach](https://pubmed.ncbi.nlm.nih.gov/23673460/)。
页面保留手动开始和光敏性提示，相关依据见
[Epilepsy Foundation 的光敏性说明](https://www.epilepsy.com/what-is-epilepsy/seizure-triggers/photosensitivity)。

## 源码与恢复

本地主要文件：

- `pynq_guardianloop/ssvep_free.py`：自由选择状态机、证据确认和撤销。
- `pynq_guardianloop/ssvep_free.html`：四角页面、时序预检与刺激控制。
- `pynq_guardianloop/ssvep_cue_runtime.py`：采集进程回调和本地接口。
- `pynq_guardianloop/guardianloop_web.py`：主页与接口代理。
- `pynq_guardianloop/test_ssvep_free.py`、`test_ssvep_free_browser.js`：软件验证。
- `eeg_apps_z15/deploy_ssvep_free.py`：备份、测试、安装、校验和回退。

板上恢复包：`/home/xilinx/ssvep-free-uyAXXT`。
本地同名证据目录的 `package/rollback_original` 保存原文件，`transaction.json` 保存新旧哈希。回退命令（仅在需要恢复旧网页时执行）：

```bash
sudo /usr/local/share/pynq-venv/bin/python3 /home/xilinx/ssvep-free-uyAXXT/mi_rms_bundle.py rollback --bundle /home/xilinx/ssvep-free-uyAXXT
```

回退会短暂停止/恢复采集与网页，恢复本次接入之前的 MI 正式版本；不重载 PL。旧 MI 集成包的回退保护会检测到新的网页文件，应先回退本次 SSVEP 变更，再考虑更早版本。

板上可能保留错误的日历时间（2021）；时效和显示对齐检查使用单调时钟，文档日期使用用户时区的 2026-10-03。
