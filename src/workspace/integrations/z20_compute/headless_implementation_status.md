# 无屏静音准备：实施记录

当前工作继续按用户批准的八阶段计划推进，整项任务未完成。主线为 Z15 负责人的输入、交互及原控制，Z20 负责辅助计算和外部感知。当前电脑暂代 Z15。真实 Z15 安装、无线关联、实体按键、HDMI 目视、棋盘标定和平板切图保留返场验收。

## 已取得的证据

| 项目 | 实际结果 | 证据 |
|---|---|---|
| 当前板卡基线 | 内核配置、运行 DTB、SD 内核/PL/DTB 已复制并计算摘要；运行状态已保存 | `report/headless/baseline.json`；SD `navigator-bringup/headless-baseline-20261025` |
| 特征接口 | 180/20/40 维特征消息使用协议 v2；旧原始脑电协议测试保留 | `tests/test_feature_input.py`、`tests/test_protocol.py`、`tests/test_service.py` |
| 录制特征 | 原预处理实际取得 19 个情绪窗口、20 个疲劳窗口 | `artifacts/headless/lemon_features.json`；`prepare_feature_replay.py` |
| 情绪参考复现 | SEED 线性权重转成 180→32→3；19/19 类别与原模型一致，其中量化校准外 10/10 一致 | `artifacts/headless/models/agreement.json` |
| 疲劳候选 | HGB 教师按 0.35/0.70 分档，使用明确标识的合成特征探针拟合；独立录制窗口 18/20 与原模型一致 | 同上；模型保持 `source_kind=synthetic`、`deployable=false` |
| 实板 NPU | 两轮各 39 个真实 TCP 输入经过 PL，逐窗口与 PS 整数参考一致；过期队列修正后另复测 39 个窗口 | `report/headless/wired_replay.json`、`wired_replay_with_camera.json`、`wired_replay_after_expiry_fix.json` |
| 断线清空 | 客户端退出后，板端情绪/疲劳均无有效分类 | `report/headless/post_disconnect_status.json`；后续软件测试也清空 PS 对照类别 |
| 相机与无屏预览 | 单一相机进程持续采集；同一渲染帧发布 PNG 并比较活动显示缓冲；PC 解码像素摘要与实际缓冲一致 | `z20_compute/person_dog_runner.py --preview --verify-display`；`report/headless/verified_headless_frame.json`、`.png` |
| 静音文件分析 | WAV→特征/波形/音量/FFT；板端特征路径无需 SciPy、新版 NumPy 或 Python cv2 | `tests/test_headless_inputs.py`、`tests/test_audio_file.py` |
| 实板声音文件链 | 318 个 WAV 在 ARM 提取特征并实际调用 PL；PC/ARM 特征最大差值 0，所有 PL 输出与 PS 整数参考一致；静音拒识且不调用 NPU | `report/headless/recorded_audio_npu.json`；分类质量与计算一致性分别统计 |
| 软件按键 | 50 ms 消抖、0.8 s 长按、启动按住等释放、九页顺序；切页不重置特征窗口 | `tests/test_headless_inputs.py`、`tests/test_feature_input.py` |
| Z15 适配副本 | 自动重连客户端、可撤销特征钩子、原文件版本预检及回退说明，独立解包导入检查通过 | `artifacts/z15_auxiliary_adapter.zip`；`tests/test_z15_adapter_bundle.py` |

LEMON 记录缺少本项目情绪/疲劳真值。以上情绪/疲劳百分比属于教师一致性。疲劳录制窗口的原模型分布为清醒 18、轻度 2、重度 0，未补造缺失等级。

## 核心长检查与驱动构建

`verify_headless_link.py --host 192.168.1.20 --seconds 1800 --output report/headless/wired_npu_camera_soak.json` 已运行 1800.625 秒，1798 个窗口全部完成 PL/PS 对照，5 次断线重连，错误为 0。状态采样 RSS 为 21348–22092 KiB，采样时待处理任务为 0，相机预览持续可用。该轮覆盖有线脑电特征及真实相机预览，不包含后来加入的声音文件、全部页面或无线关联。后续修正了延迟网络泵可能发送已排队旧有效结果的问题，失败测试→修正→复测通过，并另跑了真实板 39 窗口；最终合并版本仍须联合检查。

USB 模块已确认具有匹配驱动设备表的 `0bda:b733` vendor-specific 接口。已固定驱动源码提交 `2d9048be60759206b8db5e2370420333ef0b8478`，准备 Xilinx 2020.2 内核源及独立 ARM 构建工具。板端构建工作区为 `/root/z20-wifi-build-20261025`，日志 `/tmp/person-dog-two/wifi-native-build.log`，状态 `build.json`。构建脚本不安装或加载模块，不替换内核/PL。首次工具包硬链接前缀错误已通过红绿测试修正；独立 ARM GCC 已成功编译并运行测试程序。随后发现 m4 缺少 libsigsegv，已按包依赖补齐传递库并恢复构建，避免重复解压已核对内核源。驱动尚未记为编译、加载或无线联网通过。

## 尚需完成的实施项

1. 完成当前驱动构建，核对 vermagic/符号版本，验证加载、卸载、重新识别与无线接口出现；热点关联留现场。
2. 完善疲劳候选的一致性；声音已取得 49 份公开录音并按源录音分组，318 个文件的 ARM/PL 计算链验证完成，但首轮独立窗口分类约 52.3%，仍需改进。当前声音模型属于候选，不能凭公开来源或整数一致标记识别质量通过。
3. 把视觉、测距、点云与声音结果接入统一结果消息；保留未标定米制结果无效。板载采音及 MC8008 保持接口/诊断准备范围。
4. 将软件导航与实体 GPIO、九页详情、统一板端渲染接通。目前无屏预览是实际相机页面，尚未覆盖全部任务页。
5. 完成各启用任务独立就绪判断、暂停/冻结/停止/异常路径和联合运行检查。暂缓的人脸、MC8008 不阻塞其他任务。
6. 将 Z20 程序、兼容依赖、驱动、模型、素材、客户端与运行配置合成正式发布包；完成摘要、独立解包启动、停止、诊断与恢复检查。当前 `headless-work.zip` 是阶段部署包，不是最终交付。
7. 补齐 Z15 工程副本的具体接入位置及返场检查表。当前适配包尚未安装到真实 Z15。

## 当前运行与复现入口

板端维护 IP 为 `192.168.1.20`，数据端口 9020，无屏页面 `http://192.168.1.20:9021/`。当前页面来自板端服务；未启用正式自启动。S3 9000、原控制权和原网络配置保持原状。

电脑回放：

```
python -m z20_compute.feature_replay --host 192.168.1.20 --features artifacts/headless/lemon_features.json --output report/headless/wired_replay.json
```

同一数据端只接一个发布者；运行长检查期间不要另起回放，避免混入验收过程。

2026-10-25 工程级 `verify_offline.py` 最新整组检查时，新模块共 153 项，151 通过、1 跳过、1 错误；既有连续视频 9 项、延迟视频 1 项通过。错误仍来自旧 Z15 基线摘要：`integrations/vision_demo/device_control_baseline.json`、其安装测试、根 README 和 `docs/status.md` 已与 10 月 22 日记录不同。未修改这些文件或重写旧摘要。之后新增的延迟泵、传递依赖与精简板端无 wave 模块检查分别完成红绿测试；最终交付仍需汇总最新检查。


## 续作时的运行位置

当前板端核心服务工作目录 `/tmp/z20-headless-work`，相机素材仍在 `/tmp/person-dog-two`，相机进程1245持续发布 `/tmp/z20-headless-work/frame.png`。声音板测目录 `/tmp/z20-sound-check`，已包含修正后的无 wave 依赖解析器。PC最新源码还含后续变更，正式发布时必须统一重打包，不能直接把任一临时目录当成最终包。

电脑维护HTTP为 `192.168.1.102:8767`，发布本工程 `artifacts/`；板端证据HTTP为 `192.168.1.20:8766`，发布 `/tmp/person-dog-two`。它们仍供构建/取回证据使用。原核心长检查进程已经正常结束且 `passed=true`，不要重置该证据文件。Wi-Fi原生构建已通过 prepare/modules_prepare，内核 release 与当前板相同，正在真实生成内核/模块符号表；先核对 `/root/z20-wifi-build-20261025/build.json`、对应 PID 和日志，再决定后续动作。

实体按键尚未操作。`report/headless/software_keys_board.json` 只验证真实网络软件事件的九页状态切换、KEY2详情、长按回总览及后台窗口保持，不代表九页完整渲染或实体按键通过。
