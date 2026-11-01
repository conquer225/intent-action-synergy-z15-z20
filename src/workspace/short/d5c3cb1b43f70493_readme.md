# 脑控＋眼控隔离共存候选（2026-10-05）

## 范围与当前边界

目标是保留固定八通道脑控和原 Tobii 标定、选区、媒体功能，让两套应用在 Z15 同时运行。当前只开展已授权的临时 PL 切换和回退测试；没有修改正式代码、模型、服务、SD 启动镜像，没有生成新的 bitstream，也没有安装或加载额外驱动。

板卡为 Alientek Z15 / xc7z015clg485-2，Linux 为 5.4.0-xilinx-v2020.2。脑控正式版 `guardianloop-fixed8-mobile-web-20261003` 的滤波/SQI、情绪、疲劳、SEED、SSVEP、运动想象都运行在 ARM；当前帽位不使用历史 GuardianLoop PL DE/HGB 核。这是允许临时把 PL 用于眼控 HDMI 的前提，不是把两个完整 bitstream 同时加载。若以后启用脑控 PL 滤波/DMA，本候选会拒绝启动，必须重新评估或合成真正的共存设计。

固定八通道始终为 `F3,F4,C3,C4,T7,T8,O1,O2`。模型、通道顺序、质量与过期门限均不因共存测试而改变。没有启用实体执行器控制。

## 路径

- 本机原文件快照：`D:\ican\codex_project\brain_eye_coexist\output\snapshot_20261005_03`。脑控 release 的 48 个文件哈希核对通过；快照不是完整 SD 镜像。
- 本机候选：`D:\ican\codex_project\brain_eye_coexist\candidate\eye`。
- 板端正式脑控：`/home/xilinx/jupyter_notebooks/guardianloop_pynq`。
- 板端原眼控：`/home/xilinx/tobii_z15`。
- 板端隔离候选：`/home/xilinx/brain_eye_coexist_20261005/eye`；不自启动。其 `media`、`bin` 链接指向原眼控素材与播放器，测试只读取它们。
- 原始验收记录：本目录 `output/<run>/report.json`、`eye.log`、`preflight.txt`、`unit.txt`。退出码成功只说明程序完成及回退成功，不代表性能或识别准确率通过。

板端两份早期 tar 备份 `brain_eye_backup_snapshot_20261005_01.tar.gz`、`...02.tar.gz` 因传输中断没有完成校验，不能用作恢复依据；未删除它们。

## 避免相互覆盖

不要用原 `display_session.sh` / `start_local_media.sh` 启动共存：该启动流程会停止脑控采集服务。隔离候选绕过这个启动器，但保留眼控原来的标定、菜单、停留选择和媒体逻辑。

候选进入前核对脑控 release、当前启动自检、ARM 后端、进程配置、眼控 bit/HWH，并拒绝已存在的脑控 DMA keeper。显示使用单实例锁；PL 使用独占配置锁。借用模式由测试管理进程统一持有 eye PL，子任务不重复下载/恢复 bitstream。结束时先停止显示 DMA，再释放 framebuffer，最后恢复原 GuardianLoop PL。

原正式启动服务尚未接入新的 PL 配置锁。禁止同时进行 JTAG 下载、重载正式 PL、启动其他 Overlay 或更换 SD 卡。热插拔 SD 卡不属于支持操作。

## 复现（当前板卡，有限临时测试）

这些命令使用已保存的 `GuardianLoop-Z15` 无线配置和 SSH 凭据；结束后恢复本机 `JLU.WIFI`。硬件测试需要对应的临时 PL 切换授权。每次测试后先确认 `pl_restored`、`services_unchanged`、`protected_files_unchanged` 都为 true，且 `needs_attention` 为空，才能进行下一次。

```powershell
cd D:\ican\codex_project
& '.\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 -m unittest discover -s brain_eye_coexist/candidate/eye/tests -p 'test_*.py'
& '.\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 brain_eye_coexist/run_board_acceptance.py software --run softwarecheck
& '.\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 brain_eye_coexist/run_board_acceptance.py launch --run exampleusb40 --seconds 40 --locate --shared-pl
# 等有限板端任务自然结束后收集，不要重复使用同一 run 名称。
& '.\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 brain_eye_coexist/run_board_acceptance.py collect --run exampleusb40
```

软件检查不会打开 USB、启动显示 DMA 或下载 PL。`--locate` 是原眼控的非标定定位诊断，不会证明注视选区已成功。无人在眼控模组前时，USB 数据包数大于零也不能解释为有效眼位。

## 尚不能声称通过的部分

实际双眼标定、左中右停留控制、声音听感尚需现场验收。当前 ALSA 列表没有声卡，不能声称语音/音乐已经出声；不擅自安装或加载驱动来掩盖这个缺项。

有限测试覆盖正常结束及受控退出，不等于进程 SIGKILL、掉电、任意 JTAG 覆盖和全部 DMA 生命周期已经验证。正式开机配置仍保持原样，未将候选提升为常驻服务。

台架/运行负载只用于验收工程行为，不用于证明脑控或眼控识别准确率。当前实时脑控存在部分质量拒绝窗口，不能把本次测试描述为所有模型持续正常预测的完整负载验收。

## 已记录的工程结果

截至视频优化对照完成，正常有限测试结束均恢复原 GuardianLoop PL；每次测试前后脑控 PID 5917、网页 PID 699 及各自重启计数保持一致，82 个受保护原文件哈希不变。各测试窗口没有新增丢包、序号缺口或脑控流重置，网页抽查均返回 HTTP 200。这不代表整个工作期间从未发生过重启：初始审计之后、这些有限测试之前脑控曾由 PID 700 自动变为 5917，既有重启计数为 1。

原来任务退出就重新下载 PL 的 `usb60` 试验在回退附近测到约 3.04 秒输入延迟，不能按成功退出码认定不影响脑控。改为管理者统一持有 PL 的 `residentusb40`，USB 诊断阶段采样最大输入年龄约 1.68 秒；收到 580 个诊断样本，但左/右/双眼有效数均为零，未验收个人注视方向。

视频 `residentmedia30` 播放 102 帧、10 帧/秒、10.2 秒素材，实际呈现 37 帧，处理循环平均 282.54 毫秒；逐项定位主要开销在渲染。尝试 NumPy 替代最近邻缩放时，猜测的取样网格与 Pillow 输出不一致，未采用；改用 Pillow 自身生成精确网格后虽像素一致，但实测更慢，也未采用。正式缩放/色彩逻辑没有换成这个试验方法。

候选增加 `Renderer.render_into`：直接更新未显示的 framebuffer，静态外壳只在必要时复制，不写当前显示缓冲区。三缓冲轮换、画面内容、距离提示、菜单、播放时间、停止行为均保持原语义。新增像素一致性测试覆盖三缓冲轮换、跟踪提示开关/变化、菜单往返、标题变化与空帧。

对应 `directmedia30` 实测呈现 50 帧、处理循环平均 200.41 毫秒，循环耗时比 282.54 毫秒下降约 29%。脑控输入年龄采样最大约 1.54 秒，没有新增丢包。仍未达到素材原定 10 帧/秒，不能声称视频性能已完全合格。两次是先后运行的台架对照，不是多轮统计性能保证；输入年龄每两秒抽查一次，不能排除抽查间隔内其他尖峰。

`stopusb40` 是保留的失败试验：按进程启动计时 10 秒发 SIGTERM 时程序尚未进入就绪日志，退出码 -15，不能证明运行期清理逻辑通过；管理者仍恢复原 PL，脑控/原文件未变。后续退出试验改为等 HDMI 和 USB 阶段日志就绪后才发送退出信号，并要求报告包含 `candidate_stop_ready_confirmed=true`，不会把启动前终止算作运行期恢复通过。

本机和板端最新软件回归均为 49 项通过。板端原始证据是 `output/boardregression49/software_report.json`：测试用时 73.288 秒，原服务 PID/重启计数及受保护文件未变。`live_state.json` 保存收尾时的 PL/采集/网页状态。汇总命令不改变板卡：

```powershell
& 'D:\ican\codex_project\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 D:\ican\codex_project\brain_eye_coexist\summarize_acceptance.py
```

汇总位于 `output/acceptance_summary.json`，保留原报告路径和哈希、各阶段抽样延迟、计数器增量、失败试验和未验证项。

`stopready60` 已取得完成报告：HDMI 正在输出、USB 已进入 locate 阶段后收到 SIGTERM，眼控日志出现 `guide_stopped`，退出码 0；管理者恢复原 PL，脑控/网页进程与原文件哈希不变。该结果只证明这次受控退出，不能推广到 SIGKILL 或掉电。

首次板端软件检查有一项失败：视频 EOF 用例把创建 JPEG fixture 的时间也算入播放时间，实测 1.5879 秒超过 1.5 秒。候选仅将 fixture 创建移至计时之前，1.5 秒限制和播放器实现均未放宽；后续板端 47 项检查通过。一次后续 SSH 检查在传输中断后未取得完整结果，不计入通过。

## 下一次推进

优先继续解决视频 10 帧/秒预算，而不是修改眼控/脑控判定门限。之后需要一次实际眼控模组前的标定与左中右选区、以及接好声卡后的出声确认；这部分不能由无有效眼位的 USB 台架数据替代。

正式常驻前还需要统一 PL 所有权、准确的运行角色状态，以及脑控重启/眼控异常的独立恢复策略。当前保守 guard 在脑控进程变化时结束候选眼控，会牺牲眼控连续性来防止未知 PL 使用冲突，因此不是已完成的互不干扰故障隔离。永久启动配置须另行确认后再改，不能凭临时切换授权直接改 SD 启动镜像。

收尾未留下运行中的眼控候选或额外 PL。当前 PL 为原 `guardianloop_pynq.bit`，采集/网页均 active；`output/boardregression49/settled_state.json` 的后续连续抽查仍有包数增长、无新增丢包/序号缺口/流重置，最后一次输入年龄约 240 毫秒。本机无线已恢复 `JLU.WIFI`。原程序和所有启动配置继续保持原样。
