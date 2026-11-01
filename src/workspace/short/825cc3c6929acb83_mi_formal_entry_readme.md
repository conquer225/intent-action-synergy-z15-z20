# Z15左右手MI实验入口：安装、开关与恢复

正式ARM程序已具备实验MI入口，但交付开关为false，不自动生成MI预测，也不会控制灵巧手。原情绪、疲劳、SEED／SSVEP流程保留。固定CH1–CH8为`F3,F4,C3,C4,T7,T8,O1,O2`；MI在ARM，不在PL。

## 当前可打开的页面

- 有线／原局域网：`http://192.168.2.99:9102/mi-cued`。
- 连接板卡`GuardianLoop-Z15`热点后：`http://192.168.50.1:9102/mi-cued`。

页面明确“默认关闭”，按钮禁用。`/api/mi-cue`无旧结果、无第三类休息预测。网页不提供开启开关、上传EEG或伪造模型结果的接口。

## 以后明确要开启时

在板端编辑`/etc/default/guardianloop-mi.json`：

```bash
sudo nano /etc/default/guardianloop-mi.json
```

该文件只能是`{"enabled":false}`或`{"enabled":true}`，不能加入端口、模型路径等其他字段。将false改为true并保存后：

```bash
sudo systemctl restart guardianloop-cyton.service
```

然后重新打开MI页面。主循环按原固定通道读取同一Cyton串口，MI工作进程只监听`127.0.0.1:9104`，正式网页代为展示；不依赖电脑计算或SSH转发。配置true只代表准许实验，不证明正在收到脑电。Cyton未开机/未有合格数据时不会产生候选，网页/进程会撤销旧结果。休息不调用模型，提示不强制左右手答案。

关闭时把配置改回false并重启同一采集服务，再刷新页面。更改配置后不要省略重启：工作进程是在采集启动时创建/关闭的。当前会话**没有开启过正式MI**。

原采集曾在关闭时卡住，新增drop-in明确20秒停机上限、只清理该服务整个进程组。该保护可能强制退出，不能称底层USB堵塞已根治或无损优雅保存；正在记录时应先在网页停止记录。

## 版本与开机自检

新发布ID为`guardianloop-fixed-cap-mi-entry-20261002`。发布清单包括35个程序、模型和原PL配套文件，已单独校验摘要及原ARM模型。原 `.bit/.hwh`、设备树、驱动、启动服务原文、`BOOT.BIN`/`image.ub`/`boot.scr`均未更改；没有重新加载PL或重启板卡。

因此当前 `/run/guardianloop-startup/status.json`仍是原启动版本，**没有伪造新版本的完整开机验收**。网页标明“ARM版本已更新；新版本完整开机自检待下次启动”。以后正常开机时原启动服务会校验新发布清单并按既有流程加载同一正式PL；本轮不安排这个动作。

MI使用上一轮通过工程数值/负载验收的未晋升EEGNet，改善关口仍失败。台架回放、网页“与提示一致”和模型分数都不是新的跨人或佩戴准确率。

## 新交接／恢复包

`D:/ican/handoff/GuardianLoop_MI_ENTRY_20261002.zip`另存，不覆盖两个旧ZIP。

- `BASE_FROZEN_20261001.zip`：原冻结工程和系统恢复资料，含此前匹配的FPGA源码及bit/hwh；本轮没有重新综合或生成比特流。
- `runtime/`：新版本35项程序/模型/原PL配套及发布清单。
- `systemd/`：默认关闭的MI配置和新增30-mi-entry.conf；既有启动/网络配置见原冻结包，不需重新烧写。
- `rollback_original/`：本轮替换的原采集程序、网页与清单。
- `evidence/`、`SHA256SUMS.txt`：测试、部署、保护与逐文件摘要。旧冻结包和旧实验包摘要仍保持不变。

不是完整SD镜像，不在不兼容镜像/别的目录上强行恢复。先在原PYNQ系统/克隆卡解压包，再在板端运行只读预检（将下面解压路径替换为实际路径）：

```bash
python3 /home/xilinx/GuardianLoop_MI_ENTRY_20261002/restore_mi_entry_bundle.py check
```

只有确认需要恢复当前ARM或回退旧ARM时，分别运行下面其中一个命令：

```bash
sudo python3 /home/xilinx/GuardianLoop_MI_ENTRY_20261002/restore_mi_entry_bundle.py restore-arm
sudo python3 /home/xilinx/GuardianLoop_MI_ENTRY_20261002/restore_mi_entry_bundle.py rollback-arm
```

脚本要求原启动oneshot已active、受保护boot/PL/其他文件一致；拒绝覆盖别人的新改动。仅停止/恢复这两个ARM服务，不运行Vivado/JTAG、PL加载、设备树/驱动操作或重启。回退新增文件移到自己的`withdrawn-mi-*`目录保留，不删除。恢复当前版本的开关固定false。

恢复脚本的只读预检将在本轮板端检查；若未实际执行restore/rollback，不将其写成已通过整套实体回退演练。先完成当前默认关闭版本交付，后续真实MI合并验收再安排佩戴。

## 后续完整开机验收已完成（2026-10-02）

上文“尚未重启／待下次启动”是安装当时的历史状态。之后用户明确授权一次正常重启；新boot_id为`7f1df954-4f04-4a76-aedd-947ab69a7e2b`，新版本35项自检ready，原正式PL自动加载、标识及保护摘要正确，网页待开机标识已消失。五个服务均enabled，网页/热点/DHCP正常；Cyton关闭时采集按原5秒无包超时及15秒自动重试策略运行，并不代表收到脑电。

MI仍默认false、无工作进程监听/旧预测/外设控制。板端热点服务及本地热点地址接口已核对；本轮没有重新拔网线做客户端无线隔离。恢复脚本只读预检已通过，实体恢复未执行。

原恢复ZIP保持不变；另附`D:/ican/handoff/GuardianLoop_MI_ENTRY_BOOT_ACCEPTANCE_20261002.zip`。详情见`output/mi_boot_acceptance_20261002/RESULTS.md`与`VERIFICATION.json`。本轮部署收尾冻结，不自动继续训练、候选PL切换或佩戴测试。
