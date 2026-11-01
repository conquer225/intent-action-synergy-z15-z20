# 我们意念合一：脑电处理演示页

本更新叠加在 20261017_03 原工程和本次眼控灵巧手、倒立摆版本上。综合控制台增加 `/eeg-demo` 入口，原控制台、脑电详细页、眼控和媒体入口继续保留。演示页使用本地 HTML/CSS/JavaScript、Canvas 和 SVG，无外部字体或网络资源。

## 查看页面

电脑本地预览：在本目录运行 `python tools/preview.py`，打开 `http://127.0.0.1:9128/eeg-demo`。预览明确显示未连接设备；不生成脑电、疲劳或情绪结果。板端安装后，从原综合控制台的“脑电演示”链接进入，会继承原访问码。也可在原控制台地址后添加 `/eeg-demo` 并保留原 `#访问码`；沿用现场端口，默认脚本参数和已部署服务端口可能不同。

页面左侧显示固定八通道、原始与滤波后波形，中央显示滤波、疲劳 8 秒窗口和情绪 12 秒窗口、实际计算特征，右侧显示模型结果与信号质量。疲劳分数为模型原始输出，阈值为 0.35/0.70；情绪显示正向、中性、负向及 funny/calm/boring/horror 原分类，没有概率百分比。特征细节中的 `feature_window` 指向真正计算那次特征的窗口；它可能早于正在收集的窗口。

点击“录屏模式”隐藏记录工具；“全屏”使用浏览器全屏。1920×1080、1366×768 主画面无需纵向滚动。手机竖屏按阅读顺序排列，可向下浏览。

## 真实记录和回放

默认进入实时模式。连接有效数据后点击“开始记录”，结束后“导出”；记录保存在当前浏览器内存，刷新会清空。每次最多 10 分钟，并有 64 MB 内存保护。记录包含实际收到的展示波形、时间、通道、250 Hz 采集率、实际展示率、处理摘要、结果和缺失区间。它是展示遥测记录，不能替代无损采集档案。

“历史回放”或手动导入记录文件后才能回放，始终保留历史标识，可播放、暂停和拖动时间轴。超过三秒的缺口显示断流，不跨缺口延续旧结果。返回实时后先清空历史结果，再等待新观测。回放没有采集、校准或执行端写接口。

初始素材列表为空。`report/screenshots` 为明确标注合成输入的界面测试截图，不是受试者记录；测试临时导出的 JSON 不进入交付素材列表。

## 安装与回退

完整 ZIP 保留原工程和历史 `eye_c3_update/`；本次统一更新位于 `eeg_demo_update/`。本次只执行 `install_demo.py`，它同时包含眼控设备功能。`runtime/`、`brain_runtime/` 是可审阅源码集合，实际安装以 `update_manifest.json` 的 18 个文件为准；安装器会再成套生成发布清单、共存校验摘要、显示入口的 formal_hashes 和启动摘要。

先从原手机面板结束显示会话，等待显示停止、缓存释放、原 overlay 恢复。再停止当前部署的媒体网页服务和脑电采集服务，确认对应进程退出；服务名按现有部署核对，正式采集服务名是 `guardianloop-cyton.service`。安装器在 Linux 检查活动进程和退出记录；不要在运行时覆盖文件。

把本更新目录复制到 Z15，使用原 PYNQ Python 执行预检。下列三个根目录来自包内运行布局，应与现场一致；S3 地址必须从现场 `link` / `stream status` 确认：

```sh
cd /home/xilinx/eeg_demo_update
sudo /usr/local/share/pynq-venv/bin/python3 install_demo.py \
  --media-root /home/xilinx/gl-hdmi-live-20261008-ea117349 \
  --brain-root /home/xilinx/jupyter_notebooks/guardianloop_pynq \
  --eye-root /home/xilinx/brain_eye_coexist_20261005/eye \
  --s3-host 192.168.4.2
```

核对预检列出的文件，再以相同命令增加 `--apply`。保存输出的 `INSTALLED_BACKUP` 路径。已有设备配置保留；仅首次缺少配置时使用 `--s3-host`。未知基线、模型摘要不匹配、私有状态缺失时会停止，不能用示例状态覆盖现场文件。原权重、采样、控制协议、bit/HWH 和网络配置保持原样。

安装后按原部署启动流程恢复服务，查看 `guardianloop-startup` 状态，再从控制台进入演示页。正式启动自检仍由原启动器执行，其 PL 加载行为保持原来约定；本机文件校验不会代替板上启动验收。界面真实数据经固定 `127.0.0.1:9102` 的 `/api/status` 和 `/api/telemetry` 获取，每秒刷新一个共享缓存，数据过期后清除结果。

需要回退时同样先结束会话并停止服务，用相同三个根目录加下列参数：

```sh
sudo /usr/local/share/pynq-venv/bin/python3 install_demo.py \
  --media-root /home/xilinx/gl-hdmi-live-20261008-ea117349 \
  --brain-root /home/xilinx/jupyter_notebooks/guardianloop_pynq \
  --eye-root /home/xilinx/brain_eye_coexist_20261005/eye \
  --rollback /home/xilinx/gl-hdmi-live-20261008-ea117349/.eeg-demo-backups/install-实际目录名
```

回退会同时恢复清单、共存校验、入口摘要及新增文件。安装后文件又发生变化时会拒绝覆盖，包括开机流程已改写的状态文件；应先对照备份核查这些差异，再由维护者合并恢复。写入异常会恢复本次已替换文件；突然断电仍需凭备份检查恢复。

眼控控制链仍是 Z15 网口经桥接进入 C3 热点局域网，再访问 S3 TCP 9000；C3 热点地址不是 TCP 控制端。详细眼控菜单、启用回执和桥接说明见历史 `eye_c3_update/README.md`。本次修正了忙碌链路拒绝请求时仍显示“已提交”的提示。

## 验证入口

2026-10-19 增加用户明确要求的调试保持模式。eye_devices.json 可设置布尔值 `debug_hold: true`；视线移开和显示续约超时不再自动撤销已启用的设备，设备页面显示“调试保持”。切页、暂停、停止并返回和网络断开仍撤销控制，S3/STM32 原失联停止保留。未配置该字段时保持原 300ms 显示/眼控续约策略。启用本身只同步中立，运动仍需新选择。

已有本演示更新的 Z15，先停止显示并确认清理，再停止媒体与采集服务。使用相同 media、brain、eye 根目录执行 `install_debug_hold.py --mode debug` 预检，通过后加 `--apply`。`--mode normal` 可恢复正常模式；每次都核对已知源码、配置与发布摘要，建立事务备份并更新启动摘要。该维护安装器位于本更新目录，不能在运行中的显示进程上覆盖文件。模式切换后重新启动显示，再进行眼控标定和显式启用。

运行 `python run_tests.py`，依赖 Python、NumPy、SciPy、Pillow、Node 和 GCC。运行 `python tools/preview.py` 后可用 `node tests/browser.cjs` 重做浏览器检查，需 Playwright 和浏览器；可设置 `PLAYWRIGHT_MODULE`、`BROWSER_PATH`。浏览器测试只在测试进程中截获只读请求并提供合成输入。

检查范围、发现的问题及待实机项见 [自检报告](report/self_audit.md)，原始输出在 `report/`。模型输出用同一输入与原包实现逐项对比。Windows 跳过一项依赖 termios 的原采集主循环测试；Z15 性能、真人识别、网口桥接和真实机构动作需设备连接后验收。

资料来自用户工程包、包内最新保存运行目录及本次实际测试。AI 辅助实现和整理；软件测试截图与真人、板上结果分别记录。
