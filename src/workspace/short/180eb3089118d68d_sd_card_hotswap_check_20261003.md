# SD 卡更换只读检查（2026-10-03）

## 请求与操作边界

用户更换 SD 卡后，询问卡内配置能否运行当前程序、是否需要重新烧录。
本次仅通过已知串口 COM14（115200，DTR/RTS 不置位）进行读取，未烧录、
加载 PL、重启板卡、修改板端文件、安装依赖或修复文件系统。

## 已确认

- 用户确认：**板卡运行中直接换卡**，不是断电换卡后重新启动。
- 串口仍能出现 `xilinx@pynq:~$`，但根分区读取异常。
- 串口诊断原文摘录：

```text
EXT4-fs error (device mmcblk0p2): __ext4_find_entry:1530: inode #12: comm bash: reading directory lblock 0
systemd-journald[125]: Failed to rotate /var/log/journal/236dbcc4a6dba1caa1d5d5bc61955d45/system.journal: Read-only file system
-bash: /bin/cat: Input/output error
-bash: /sbin/ip: Input/output error
-bash: /bin/systemctl: Input/output error
```

- 因外部命令读取失败，未取得本次 boot ID、服务状态、卡内应用版本和文件校验值。
- 随后尝试用 shell 内建命令读取 `/proc`；串口日志刷屏期间长命令输入不完整，
  返回语法错误。该尝试没有取得有效核对数据，不能据此报告挂载参数或卡身份。

## 推断与未知

- 当前现象与运行中移除 Linux 根文件系统所在卡一致。已在内存中的进程或旧网页
  仍可能存在，不能证明替换卡内程序已启动。
- 尚不能判定新卡本身损坏，也不能判定其 ARM 程序、模型、服务、PL 文件是否齐全。
- 前一次正式重载的验收结果不能作为新卡的验收结果。

## 下一步

请用户关闭 Z15 电源，确认要测试的 SD 卡插稳，再重新上电；运行中的启动卡不要
再次直接拔换。冷启动后，重新只读核对系统、应用清单、Python 依赖、服务、
启动状态与正式 `.bit/.hwh` 文件。若需修复或迁移，先说明差异并取得相应授权。
目前没有证据支持直接重新烧录或格式化。

## 用户重新上电后的只读复查

用户回复“已重新上电”后，经 COM14 与无线 SSH 交叉核对。
SSH 地址 `192.168.50.1`，本次 boot ID 为
`0f613174-3c87-473b-9292-ace4a8c8fe00`，与串口一致，区别于此前正式重载的
`365d9217-edca-44d6-9266-83963abb1186`。板端时钟仍显示 2021 年；本记录日期采用
客户端 2026-10-03，不用板端墙钟判定本次启动。

### 已确认

- 系统：PynqLinux 2.7、Ubuntu 20.04，ARMv7，内核 `5.4.0-xilinx-v2020.2`，
  设备树机型 `Alientek Z15 Development Board`。
- SD 卡为 29.1 GiB 的 NCard，CID `8903034e4361726410abe53110017400`。
  根分区 `/dev/mmcblk0p2`（ext4）及启动分区 `/dev/mmcblk0p1`（vfat）均为 `rw`。
  没有继续出现上次热换卡时的基本命令 I/O 错误；这不等于全面介质健康检查。
- 已安装版本为 `guardianloop-fixed8-ssvep-study-20261003`，通道为
  `F3,F4,C3,C4,T7,T8,O1,O2`。
- 对本地冻结包进行比对：46 个运行文件、清单及 9 个启动/配置文件，合计
  **56/56 哈希一致**。此外两个 `20-startup.conf` 和 MI 的 `30-mi-entry.conf`
  均与本地相应发布配置哈希一致。
- 配置参考：
  `D:\ican\codex_project\eeg_apps_z15\output\ssvep_free_study_20261003\package\runtime\release_manifest.json`
  及该包 `transaction.json`；MI drop-in 正确参考文件为
  `D:\ican\codex_project\eeg_apps_z15\output\mi_formal_entry_20261002\package\systemd\guardianloop-cyton-mi.conf`。
  其 SHA256 为 `1cce574abadd5905df99b90b42c88ffc6f5b56336b91ef2e6253e72b7dbb77ab`。
- `/run/guardianloop-startup/status.json` 为本次 boot ID，`state=ready`、
  `stage=complete`、`verified_files=46`。情绪、疲劳、SEED、SSVEP、MI 等 ARM
  模型构造检查完成；MI 配置启用、个人头关闭、物理控制关闭。
- 正式 PL 由已有开机服务自行加载，并通过 ID 检查：DE `44453031`、
  HGB `48473031`、model `50537911`。本次诊断没有主动加载 PL。
  `used_by_current_cap=false`；当前固定帽位的滤波和这些模型路径仍为 ARM。
- `guardianloop-startup` 为 active/exited，采集 PID 693、网页 PID 692 为
  active/running，观察到 `NRestarts=0`；热点及 DHCP 服务运行且已启用。
- Python 3.8.2，NumPy 1.20.3、SciPy 1.3.3 可导入，PYNQ 可发现。
  初次探针误把 `serial` 纳入必需导入，得到 ModuleNotFoundError；当前采集源码
  使用 `os/select/termios`，并不依赖 pyserial，故不能据此判断程序缺依赖。
- 没有发现 `gldma` 内核模块或 DMA keeper 设备。本轮没有装载、卸载驱动。
- 主页面、`/ssvep-cued`、`/ssvep-free` 均返回 HTTP 200。
  `/mi-cued` 初次 3 秒探针超时，稍后只读复查返回 200、11,230 字节：板端
  0.027422 秒、PC 无线访问 0.053725 秒；首次延迟的精确原因未进一步测定。
- `/api/mi-cue` 返回 `source=live`、`input_state=ready`、固定八通道和已接受 RMS
  模型哈希，物理控制关闭、状态 idle。输入质量为 `signal_invalid`。
  采集状态包计数从 13,281 增长到 53,532，存在断流/质量拒绝；只说明接收与
  处理路径在运行，不证明佩戴状态、预测准确率或整套合格负载。
- PC 无线临时切到 GuardianLoop-Z15，两次诊断后均恢复并确认 JLU.WIFI。

### 保留的维护提示与限制

```text
EXT4-fs (mmcblk0p2): recovery complete
FAT-fs (mmcblk0p1): Volume was not properly unmounted. Some data may be corrupt. Please run fsck.
```

- `/boot` 的 FAT 提示意味着需要备份后安排离线检查，不表示已证实文件损坏。
  已核对的启动文件哈希一致，但未进行完整介质检查，也没有在已挂载分区上运行 fsck。
- 采集及网页服务 `NeedDaemonReload=yes`；对应目标服务与三个已核对 drop-in
  内容一致、当前进程正常。尚未查清缓存提示原因，本轮没有 daemon-reload 或重启服务。
- `/etc/default/guardianloop-cyton` 不存在；发布服务通过可选 `EnvironmentFile=-...`
  引用，现有默认固定通道和模型已通过启动验证，不能把可选文件缺失当作启动失败。
- 没有重刷 SD、复制 ARM 程序、改变模型、改写启动配置、加载候选 PL，或发起新试次。

### 本次结论

新卡冷启动后具备当前正式版运行文件及配套配置，已有开机服务完成 ARM 自检与
正式 PL 加载，网页与 MI 状态接口正常，**无需为了换卡重新烧录程序**。
若后续要处理 FAT 警告或配置缓存提示，另行取得维护授权；不要运行中再次拔换启动卡。
