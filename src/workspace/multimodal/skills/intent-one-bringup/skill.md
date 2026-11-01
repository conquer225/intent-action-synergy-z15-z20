---
name: intent-one-bringup
description: 构建、检查或接回“我们意念合一”Z15/PYNQ、S3、C3、灵巧手和倒立摆工程时使用。保留已验收原件，核对独立输入、DMA与局域网记录。
---

定位包含 intent_one、hardware 和 release/manifest.json 的工程根。先读 README.md、GLOSSARY.md、report/verification.md 和 ACCEPTANCE.md。

已验收基线来自用户提供的 GuardianLoop ZIP 和原 S3/C3 工程，来源记录在 baseline_manifest.json。新整合验收与原验收分别记录。公开作品名称用“我们意念合一”；工程别名 GuardianLoop 和历史原件保留。

在设备缺席时运行 tools/verify.py，按需要追加 --firmware-tests 和 --rtl；使用 tools/build_firmware.py 编译，使用 hardware/create.tcl 构建成对 bit/HWH。停止在烧录之前，报告实际结果和待实物项。Wi-Fi 私有头文件不进入源码包，手姿态配置保持已验收值。

接回 Z15 时先预检原 ARM 脑电服务、启动记录、正式模型哈希与显示库。统一 C3 热点：C3 .1、S3 .2、Z15 .3；改网络使用 tools/c3_station.py 的查看计划、备份和回滚入口。核对 GL_PAGE_POLICY_PATH，避免同时运行两个显示/PL所有者或两个 Cyton 读者。

主模式为眼控/肌电/脑电，PL_KEY0依次切换、PL_KEY1停止；H5/H6通过AXI GPIO输入，PS键保留原校准/暂停行为。MPU是辅助入口。眼控首页是手/倒立摆/表达与媒体，复用原音频播放器、视频缓存与评分ID。切输入和页面先停止，启用是明确操作，恢复不自动启用。眼控沿用三点训练和快速检查；SSVEP选区必须有实际 PL 显示计数和新鲜质量通过的完整窗口。情绪/疲劳/MI只显示，MI trial使用virtual_control=false。回放、模拟或过期数据不能触发执行端。

S3 9000控制、9010只读采样；C3 9001原桥接、9011只读STM遥测。网络ACK表示命令接受，机械验收需执行回传和现场确认。DMA错误先停止/复位再释放缓冲区，未确认停止时保留租用内存并结束会话。原启动镜像与设备树保持现状。

现场动作只在用户确认设备供电和空间条件后按 ACCEPTANCE.md 分项完成，记录三次60秒平衡和30分钟整机运行。保存真实日志、时间与结论，不把模拟数据、离线模型指标或源码编译通过写成实物验收。
