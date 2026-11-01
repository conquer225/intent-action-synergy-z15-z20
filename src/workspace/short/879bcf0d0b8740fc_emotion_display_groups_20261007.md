# 网页与 HDMI 心情参考展示（2026-10-07）

用户授权将已有四类输出归并展示，并去掉情绪卡片描述中的“游戏”字样。仅改展示，不改模型权重、原始类别、训练标签、质量/断流门控或歌曲提示决策。

- `funny` → 正向情绪。
- `calm`、`boring` → 中性情绪。
- `horror` → 负向情绪。
- 无效、过期、断流或未知类别 → 无可信结果/等待状态，不能当作中性。

手机卡片标题为“心情参考（模型估计）”，描述保留原始四类展示归并、个人真实情绪准确率尚未验证的说明。完整网页、统一手机媒体入口、统一 HDMI 的心情显示使用相同归类。研究录制区仍保留原始条件名称，不改变历史研究数据来源。

## 实际接入

通过以太网 `192.168.2.99` 更新以下软件文件：

- 正式目录的 `guardianloop_web.py`、`mobile.html`、`mobile.js` 及发布清单。
- 私有媒体目录的 `system_mobile.js`、`system_hdmi.py` 和十页中文菜单缓存。
- 共存守护的期望清单哈希，以及本次启动记录中的软件版本标识。没有运行启动 PL 加载或修改 SD 启动镜像。

正式软件版为 `guardianloop-fixed8-mood-display-20261007`，50 个清单文件通过校验。清单 SHA256：

`9ba637e40f3c857caa866a829720c1ed0846bbf19a372fcc40811ed9bbe030b0`

采集 PID 23531、NRestarts=0 保持不变；只重启正式网页服务，最终网页 PID 26555、NRestarts=0。启动 ID 与正式 `guardianloop_pynq.bit` 均未改变。

本地软件测试 23 项：22 项通过，1 项仅板端 C 库测试跳过。手机与完整网页的 JavaScript 测试覆盖四类归并、原始标签保留、过期/断流撤销；统一媒体页测试通过。菜单缓存十页往返逐像素一致，板端从安装后的缓存成功构造显示对象；软件预览检查文字居中、状态不出框。

板端 `/`、`/mobile`、`/mobile.js`、`/api/status` 均返回 200 和 `Cache-Control: no-store`。共存守护仍通过，没有降低哈希/通道/ARM/实体控制约束。

电脑使用无代理的以太网 `192.168.2.99:9102` 再次核验网页/手机版/脚本均为 200，手机情绪卡片没有“游戏”字样，返回的脚本与安装文件 SHA256 相同。当前实际接口为 eth0 `192.168.2.99/24`、wlan0 `192.168.50.1/24`；旧浏览器上下文中的 `192.168.43.6` 当前不在板卡接口上。本轮没有修改联网配置，不能把旧地址访问失败当作展示文件安装失败。

本轮 HDMI 会话未启动，不下载显示 Overlay、不发声、不操作眼控或轮椅。HDMI 新文字在下一次正常启动统一显示会话时使用，不应把软件预览称为实际屏幕验收。

## 恢复与失败记录

第一阶段 `gl-mood-display-S1nO56` 因网页重启后端口尚未就绪而检查失败，已自动回退；错误日志保存在本轮输出的 `attempt-1.log`。补上 12 秒限时就绪检查后，第二阶段 `gl-mood-display-MyI74a` 更新通过，安装单元及独立回退定时器均已结束。

当前原件备份：`/home/xilinx/gl-mood-display-MyI74a/backup`。需要撤销这次展示改动时，在板端执行：

```sh
sudo env XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python3 /home/xilinx/gl-mood-display-MyI74a/mood_display_transaction.py rollback
```

回退脚本拒绝覆盖后续他人的改动，只恢复本轮展示文件并重启网页，不停采集、不加载 PL。本地恢复包 `phone_video_upload/output/mood_display_20261007/display-recovery.tar.gz` 已与板端校验一致，SHA256：

`447ec6974a3b1c630a5ed5b5077ce869081ce3568336e316940118e11e07eaf6`

软件安装报告、旧文件、发布载荷及软件 HDMI 预览均保存在 `phone_video_upload/output/mood_display_20261007/`。原始模型输出仍为 GAMEEMO 四类，此次三档归并没有形成新的情绪准确率证据，也没有替代真实采集/HDMI 同场验收。
