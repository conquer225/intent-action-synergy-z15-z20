# 左右手运动想象：隔离功能候选

2026-10-02。本包仅在 Windows PC 验证，没有部署到 Z15，也不修改正式9102服务。固定 CH1–CH8 = F3,F4,C3,C4,T7,T8,O1,O2。

## 能做什么

手动左手／右手提示 → 连续有状态滤波 → 提示后的完整500样本窗口 → 硬质量门控 → 实验模型 → 如实显示结果。休息不调用分类器，不是模型的第三类。停止、坏质量、丢包、迟到、断流、页面隐藏及心跳失效撤销当前候选。

结果始终 `control_enabled=false`、`production_eligible=false`。模型原确认改善关口没有通过。本包只为接线和数值验证，不是高准确率最终模型、正式ARM模型或灵巧手控制软件。

实验权重固定取原30人研究的第一个折／第一个种子 `s01_seed42.pt`，没有挑最佳成绩或重训。NPZ须显式 `--allow-experimental` 才能加载，默认拒绝。运行仅依赖 NumPy、SciPy 和 Python 标准库，不需要 Torch、GPU或电脑端 OpenBCI GUI；但本轮尚未证明它能在 Z15 实时运行。

## 原目录启动命令（PowerShell）

```powershell
Set-Location -LiteralPath 'D:\ican\codex_project\pynq_guardianloop'
& 'D:\ican\codex_project\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 mi_cued_replay.py --model 'D:\ican\codex_project\eeg_apps_z15\output\mi_cued_delivery_20261002_final\experimental_eegnet.npz' --input 'D:\ican\codex_project\eeg_apps_z15\output\accepted_bench_load_20260927\bench_input.npz' --allow-experimental --audit-log 'mi_cued_local_events.jsonl'
```

访问 `http://127.0.0.1:9104/mi-cued`。默认只播放一遍156秒台架记录；EOF会撤销并显示没有新数据。不要据此评估人类运动想象准确率。需要反复测试按钮时才加 `--repeat`，结束按 Ctrl+C。此次验收的循环回放已停止。

仅检查无输入页面，不加载模型或回放：

```powershell
& 'D:\ican\codex_project\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 mi_cued_server.py
```

## 解压独立包后

包内 `app/` 是平铺模块，`models/experimental_eegnet.npz`、`recordings/bench_input.npz` 和 `evidence/` 分开。使用已有带 NumPy/SciPy 的 Python，不自动安装依赖或系统服务。当前实测版本见 `MANIFEST.json`。

```powershell
Set-Location -LiteralPath '<解压目录>\app'
python -X utf8 mi_cued_replay.py --model ..\models\experimental_eegnet.npz --input ..\recordings\bench_input.npz --allow-experimental
python -X utf8 -m unittest test_mi_cued test_mi_cued_replay test_mi_eegnet_portable
node test_mi_cued_browser.cjs mi_cued.html
```

`<解压目录>` 是用户实际选择的目录；不能原样执行占位符。默认仅绑定127.0.0.1，不开启外网访问。无需电脑训练集；台架数据不是此次佩戴或带MI标签的记录。

## 下一步的板端接入契约

未来隔离采集适配器调用 `CuedMISession.feed(raw_uv, sequences, received_monotonic=...)`：每批1–250行、原始µV单位、严格八路顺序、逐样本0–255包序号。未知单位、重复、缺包、迟到、换源均不能直接沿用旧窗口。断连调用 `disconnect()`。网页API没有上传EEG或伪造分类结果的入口。

250Hz、固定八路 CAR、原连续50Hz notch／1–45Hz、随后4阶8–30Hz。至少500样本热身。浏览器绘制报告到达服务器时锁定水位，随后125–625样本形成2秒输入。这不是光学提示同步，不能报告精确刺激起点延迟。训练集的512→250重采样、逐试次复位和设备参考差异仍未解决，缓存数值一致不等于真实跨设备性能一致。

硬门控复用 `channel_sqi`：八路 `flat_ratio<0.8`、`clip_ratio=0`、`p99_abs<=100µV`。不是个人MI质量校准、伪迹修复或识别置信度。不能把坏通道置零凑齐八路，也不能从提示生成答案。

下一阶段先验证隔离Z15 ARM的滤波／分数数值、内存、耗时和断流恢复，不自动替换正式服务或开机加载。板测可先回放、无需佩戴；真实左右手MI效果与执行器安全控制仍是后续独立验收。PL分工保持已有部署，不因本机成绩搬核或生成bitstream。

## 后续状态：隔离ARM已验收（2026-10-02）

以上“本机验证”的段落记录最初PC交付边界，原PC候选ZIP保持冻结。后续Z15隔离验收已完成：33项板端测试、256窗口数值比较、156秒定时回放与缺包/子进程恢复通过；未正式部署、未改PL或开机服务，准确率晋升仍未通过。板端stage为 `/home/xilinx/mi-arm-acceptance-DeB9RH`，测试进程已停。

此前“20提示=13候选+7休息”的说明应更正：实际6次休息、13完整候选和1次被EOF截断的提示。原记录首50样本有包序号跳变，应拒绝，不能编造滤波值。详见 `D:\ican\codex_project\eeg_apps_z15\output\mi_arm_acceptance_20261002_retry1\RESULTS.md` 与 `RUN_STATUS.md`，使用那里的命令复现板测。
