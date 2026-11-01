# 统一 HDMI 眼控启动检查（2026-10-07）

## 范围和流程

按用户要求缩短现场检查，不重启 30 次准确率统计。
每次开始眼控先连接模组，显示实时距离、左右眼检测率、左右瞳孔可用率。
位置确认必须收到 1.5 秒内的双眼/双瞳孔非零检测数据；距离只作参考，
不伪造固定坐姿要求，也不把检测率当作选区准确率。

按 PS_KEY0 确认位置后，沿用原生中/左/右三点方向标定。
标定完成后，独立提示中/左/右各一次。提示不参与训练或分类；原 Selection
的稳定、停留、新鲜度、边界中性带和跨页面锁定规则不变。每个提示实际 HDMI
呈现确认后等待 1.2 秒，才接收新的停留选择。第一次确认选错即失败；无数据、
过期数据和重复数据不记通过。三次都正确后自动回到原统一主页。

最后一个右区选择锁定沿用到主页，不能因仍看右边而自动连选下一页面。
菜单内按 PS_KEY0 可重新开始位置检查；PS_KEY1 停止采样并撤销待执行选择。
这三次是功能检查，不给出识别准确率结论。

## 软件和部署证据

- 本机：42 个测试运行，41 通过，1 个仅板端编译库测试跳过。
- Z15：同一组 42 个测试全部通过，无跳过；新增用例覆盖位置确认、实际呈现
  门控、三次选对、先选错失败、旧/无效/重复输入不放行、通过后保持选区锁定。
- 追加显示参数修正后的板端同组检查也退出 0；随后成功启动显示单元。
- 仅更新隔离显示副本和其原生引导 Python 渲染器，不更新原生 USB 二进制、
  分类门限、正式 EEG 代码、模型、PL 文件或开机配置。
- 更新前备份：`/home/xilinx/gl-media-20261007-314e8796/backup-eye-entry-20261007-02`。
- 现有正式采集 PID 695、网页 PID 694，均 active、NRestarts=0；正式发布哈希一致。
- 启动前确认原 PL 已恢复，旧会话及恢复定时器 inactive，EyeChip 2104:0124
  仍在 USB 上。当前 boot ID：cb00a3b7-a4c3-4f0b-b4ec-bd4302af03da。

## 安全边界

沿用 Z15 xc7z015clg485-2 与已核对 eye_wifi.bit/.hwh，原 PL 恢复目标是
`/home/xilinx/jupyter_notebooks/guardianloop_pynq/guardianloop_pynq.bit`。
临时单元 eye-flow-20261007-02.service 限时 900 秒，独立恢复定时器 950 秒；
现有退出流程停止显示 DMA、释放缓冲区后恢复原 PL。全程静音、无实体轮椅命令，
不启用 SSVEP 刺激或运动想象退出，正式 ARM 采集和网页不停止。

手机 QqqQ 热点重连成功，Z15 wlan0 地址 192.168.43.6；正式网页 HTTP 200。
正式网页“板卡热点异常”只检测本机 AP 服务；手机热点模式下该服务应关闭。
没有为掩盖提示而修改正式网页。

## 待现场确认

本轮三次记录已在退出报告中核验：中/左/右目标均一次选对，completed=3、passed=true。
软件呈现确认到选择接收分别约 3.49/3.13/4.50 秒，包含页面阅读保护和停留时间，
不是光学响应时间；这三次不能估计准确率。用户另报告“眼控一切正常”。
看中央视频不误翻页、切页不连续误选、移开视线不继续执行这三项短现场检查
仍是后续独立事项，不能以本轮三次选区检查替代。

## 本轮实时启动状态

eye-flow-20261007-02.service active、PID 30106，独立恢复定时器 active。
起初原生采样失败，并在内核日志看到 EyeChip 在 08:22:06、08:22:51、
08:23:59（板端日志时间）断开后重新枚举。现象是真实 USB 重连，物理原因
尚未确认，不据此断言供电或用户操作原因；控制状态每次失败均撤销旧输入。

之后原生采样重新连接，最后核验为 positioning、connected=true、error=null，
尚未标定/放行菜单。收到实时距离约 43.6 cm，左右眼检测 100%/100%，左右
瞳孔可用 50%/100%。该读数仅为当时半秒统计，不证明连接长期稳定或准确率。
当前原生记录：`/home/xilinx/brain_eye_coexist_20261005/eye/captures/cal_91272361bb12414da6d9a9bf3184e6d3`。
正式采集和网页仍为原 PID、NRestarts=0，网页 HTTP 200。

## 菜单停留反馈更新

用户指出统一菜单没有测试页面那样的选择进度。已确认统一菜单只缓存静态卡片，
动态键没有 Selection 的 hover/progress/locked 状态，故不能显示停留反馈。

只修改 `phone_video_upload/system_hdmi.py`、`media_player.py` 及显示测试。
每个有操作的卡片增加停留条，按现有 Selection 的实际进度以 5% 为单位更新，
显示“正在确认”“已触发，请换区”“切页保护，请稍候”“等待有效注视”。
中央视频不是按钮，不画进度条。旧输入、暂停、换页阅读保护均清零显示进度；
显示层不修改 classifier、停留/稳定门限、跨页锁或按钮含义。

缓存卡片仍复用；变化只写卡片下方的 96 行区域，每个帧缓冲区分别记录显示状态，
不因进度变化重画整页或覆盖中央视频。菜单呈现键包含进度状态，按实际绘制时间
保存键值，防止绘制后过期的进度被误当作已经清除。

本机 48 个测试：47 通过、1 个板端库测试跳过。6 个新增用例覆盖进度变化触发
重绘、正确填充比例、过期清除、三帧缓冲一致、只读锁定/切页显示、暂停与中央
视频保护。本机生成并目视核对了合成界面预览；不是实测眼动证据。
板端同组 48 个用例全部通过，无跳过（45.474 秒）。SSH 读取先达到控制端
超时，但随后独立核对完整日志末尾为 Ran 48 tests / OK，确认测试进程已退出；
源码语法检查也退出 0，不能将 SSH 超时误报成测试失败或跳过验证。

旧 02 单元已结束；systemd 最后记为 runtime timeout，但播放器报告 errors=[]、
display_halted=true、buffers_released=true、original_restored=true，PL 读回验证为
原 guardianloop_pynq.bit。不能把 systemd timeout 写成普通 service success。
源文件更新前备份：`/home/xilinx/gl-media-20261007-314e8796/backup-eye-progress-20261007-03`。

新单元 eye-flow-20261007-03.service 已启动，PID 19258、active、Result=success，
恢复定时器 active。已确认新版播放器进入 playing/video、error=null，然后
发送 eye_start 仅打开距离检查，标定仍等待用户 PS_KEY0。正式采集和网页
继续为 PID 695/694、active、NRestarts=0。新菜单进度的真人可见性和这次
重新标定尚待用户确认，不用合成界面预览冒充 HDMI 实测。
最后实时核验为眼控 connected=true、state=settle、error=null，标定已开始；
距离约 43.2 cm、左右眼检测 100%/100%、左右瞳孔可用 91%/82%，仍未放行菜单。

板端更新文件 SHA256 与本地一致：

- system_hdmi.py：5887237d6e40018897a7f8a71c5c1031e3eacfa4f69a153eb0fc627bc0c59b6a
- media_player.py：3efc76d4166c82adc687487cdda597dea93aef5b5daf5e66e2884fca08b31b57
- test_system_hdmi.py：839ea5a2228ea72b772735d15c19fad9178b0e61fc0e758b2f9e3cdad4188bd6

## 选中回执与采样中断修复（04）

### 原因核验

03 会话中，中/左/右快速检查均通过，之后确实从主页进入 speech。
原生 worker.log 出现 `usb_bulk_error code=-1`，状态记录 `native_exit_-1`；
内核同阶段有 EyeChip 断开后重新枚举。只能确认 USB 采样链路异常和进程退出，
不能据此断言是用户动作、线缆、供电还是驱动问题。03 最终正常达到 900 秒期限，
报告 errors=[]、display_halted/buffers_released/original_restored 均为 true。

显示层把所有 Selection.locked 状态映射为 100% 和“已触发”，但锁可能来自
三次检查的最后右区或上一页面。本机复现：主页选中中央进入 speech 后继续看
中央，未执行新动作却显示满条；先稳定看另一选区再看中央才会返回主页。

### 修改范围

- SystemController 为执行成功的选择保存原始 page_id、region、时间和动作回执。
  gaze 返回 choose 的真实结果；视频中央空按钮不报告执行成功。
- UnifiedDisplay 区分跨页面锁与当前页执行回执：前者为零进度及“请先看其他区，
  再选此处”，后者才显示“已执行，请换区再选”和满条。显示仍不改停留门限或
  跨页面防连选锁；speech 显示所选表达，music 显示歌曲序号，均保持静音。
- 原生错误一旦发生，后续迟到的 ready/direction_ready/gaze 不得重新放行；
  清除动作回执、待选择、半完成 MI 退出和虚拟方向。错误状态 connected/valid
  为 false，状态提供 reconnect_required、reconnect_action=eye_start 和提示文字。
- positioning/verification/selection 阶段连续超过 3 秒没有任何采样消息，
  明确转为 native_silent 中断状态。持续的无眼位 quality 消息仍属于活连接，
  不会把眨眼或暂时移开视线当成 USB 断开。连接恢复仍需用户手动开始、重新
  检查位置、标定及中/左/右三次快速检查，不自动继承旧校准和选择。
- 失败页明确显示 PS_KEY0 重连并重新标定、PS_KEY1 停止，长错误说明自动换行。
  未修改原生 USB 二进制、分类器、正式 EEG 文件、模型、启动配置或 PL 文件。

### 验证与备份

本机 57 项检查运行，56 通过，1 个仅板端编译库测试跳过；板端同组 57 项全部
通过、无跳过（57.392 秒），systemd 测试单元 ExecMainStatus=0、Result=success。
覆盖跨页锁不冒充执行、同页真实执行、表达刷新、原生错误不可复活、无消息超时、
无眼位但有数据保持连接、重建连接不继承校准、可见重连提示，以及原有显示和
控制门控。板端完整测试日志为私有目录下的 eye-recovery-check-04.log。

更新前旧文件备份：
`/home/xilinx/gl-media-20261007-314e8796/backup-eye-recovery-20261007-04`。
仅更新该私有目录里的 Python 显示、运行时和测试源，以及隔离 eye/src/guide_render.py。
本地 D:\ican 不属于 Git 仓库；不声称有 Git commit 或已更新此前队友压缩包。

### 实际启动与尚未完成的检查

04 HDMI 会话曾 active，PID 17143，状态 playing/video、error=null，已请求
eye_start 打开位置检查。尚未实施原生进程中断注入，该会话就在运行时发现
正式脑电进程 PID 改变，按共存保护退出。报告错误为：
`Runtime admission revoked: Brain process changed; end eye session and recheck before retry`。
报告再次确认原 PL 恢复、显示 DMA 停止、缓冲区释放；正式发布哈希和 boot ID
未变。正式 Cyton 服务日志明确为 `/dev/ttyUSB0` 不存在，自动重启，网页服务
PID 694 仍在运行。没有为继续测试而绕过共存保护或修改正式串口配置。

软件修复与板端回归检查已完成；真实 USB 重连和本轮真人菜单操作仍待接收器
恢复、重新核验共存准入后完成。不能把单元测试通过写成 USB 物理故障已根治，
也不能把手机按钮模拟当成眼动成功。04 恢复定时器仍有界限；旧会话恢复报告
完备时，计时器不会改写后来启动的 PL 会话。

随后确认接收器并未消失，而是重新枚举成 `/dev/ttyUSB1`；同一 FTDI 的
`/dev/serial/by-id/usb-FTDI_FT231X_USB_UART_D309LDXY-if00-port0` 指向该节点。
用户确认接收器已插好、Cyton 采集板未开机。未开机本身不妨碍眼控检查，
但硬编码的 ttyUSB0 导致正式服务持续启动失败。实际重连验证需先恢复正式
服务的串口路径；此轮尚未修改正式服务或其运行时配置，也未伪造 ttyUSB0。

## 临时串口恢复与实际重连验证（05）

用户随后授权稳定设备路径与一次正式采集服务重启。重新只读核验接收器为
FTDI 0403:6015，稳定节点
`/dev/serial/by-id/usb-FTDI_FT231X_USB_UART_D309LDXY-if00-port0`
仍指向 ttyUSB1。原有 /etc 服务和两个启动 drop-in 不变；仅新增
`/run/systemd/system/guardianloop-cyton.service.d/90-usb-port-recovery.conf`，
ExecStart 保留原 acquisition 入口及全部原参数，追加该稳定节点的 --port。
daemon-reload 后重启一次 guardianloop-cyton.service。这个 /run 配置在完整重启后
消失，不是永久安装；撤销时须仅移除该确切文件、daemon-reload，再在确认正确
串口配置后决定是否重启，不能直接恢复到不存在的 ttyUSB0 并声称恢复正常。

恢复后正式采集 PID 29506 持续 active，NRestarts 保持历史累计 27 不再增加；
不能将累计值写成 0。网页 PID 694、NRestarts=0、HTTP 200。正式发布 SHA 校验
未改变，boot ID 仍 cb00a3b7-a4c3-4f0b-b4ec-bd4302af03da，共存准入重新通过。
用户确认 Cyton 采集板关机；服务日志的 STREAM_STARTED 只代表发送启动命令，
不能据此声称有真实脑电输入。

05 会话沿用已核对的 eye_wifi.bit/.hwh、900 秒有限期、920 秒 systemd 上限和
950 秒独立恢复定时器，全程静音、eye_only、无 SSVEP 刺激、无实体控制。
显示 PID 30741。位置检查阶段只对该显示进程创建的原生眼控 worker 31215
发送一次 SIGTERM，未拔插 USB、未重启板卡、未停止正式脑电或网页。
实测失败状态 connected/valid/control_enabled=false，last_valid=null、动作回执
清空、direction=stop、半完成 MI 清空，reconnect_required=true。

通过 eye_start 发起替换后，原生新进程 32146 和新 captures 目录可见。第一次
自动检查要求每次状态都小于 2 秒，重建期间触发了过期断言；这是控制端检查
未完成，不能写成一次无条件通过。后续独立读取确认回到新鲜 positioning：
calibrated=false、control_enabled=false、quick_check=null、samples=0；证明
没有自动继承旧标定放行。继续核验时用户已自行重新标定并完成中/左/右各一次，
三次均正确，约 3.14/3.24/3.14 秒，含阅读保护和停留，不是光学延迟或准确率。

运行事件实际经过 home -> media -> video -> video_nav -> video -> video_rate，
记录到视频索引切换。该阶段眼控新鲜有效，显示不再只停留在虚假的满进度回执。
随后同一原生会话出现 usb_bulk_error code=-1，内核记录 EyeChip 在
2026-10-07 09:24:21 UTC（北京时间 17:24:21）从 USB 1-1.2 断开，下一秒重新
枚举为 device 16。运行时 native_silent 撤销输入，未继续执行旧选择；正式采集
PID 29506 和网页 PID 694 不变。这个后来发生的真实 USB 异常不是本轮再注入，
原因尚未确定，不能宣称连接故障已根治。

只读检查发现 EyeChip power/control=auto，重新枚举后已 suspended；这个读数
来自采样退出之后，不能据此倒推自动休眠导致断开。Hub 的累计 suspended time
为 0。未改 USB 电源策略、未卸载驱动、未修改原生 USB 程序；需要结合线缆、
供电和用户现场反馈继续定位。已请求用户确认是否碰动连接或按停止键。

证据保存于板端私有目录的 eye-flow-20261007-05-reconnect-check.json 和
eye-flow-20261007-05-checkpoint.json；保存后向当前 05 会话发送受控 stop，
等待其 DMA 停止、缓冲区释放和原 PL 恢复。软件回执/失效处理及串口恢复已经
验证，但实际 EyeChip 连接长期稳定性、中央视频/移开视线的专门短检查仍未完成。

05 受控退出进一步读回：errors=[]、controlled_stop=true、display_halted=true、
buffers_released=true、original_restored=true，systemd inactive / Result=success；
PL 读回为原 guardianloop_pynq.bit。正式发布与 boot ID 保持不变。
用户明确反馈这次没有碰线或按停止键，不能将该次断开归因于用户操作。

因此追加一次无需重新标定的 140 秒原 PL 连接保持诊断：隔离新脚本
`phone_video_upload/eye_usb_hold.py` 只打开既有原生 relative-selection worker，
不发送 point/compute、不出 HDMI、不发实体控制、不改电源策略或驱动。
每 5 秒记录眼控 USB devnum、runtime_status、挂起累计时间及消息数，同时
核对共存契约及原 PL；独立 systemd 单元上限 180 秒，原生清理保留 15 秒。
新增脚本本机及板端 py_compile 通过；不以语法通过代替连接保持测试结果。

已核对 [Linux 内核 USB 电源管理文档](https://www.kernel.org/doc/html/latest/driver-api/usb/power-management.html)：
打开 usbfs 文件期间设备不应被判为空闲。因此“退出后 suspended”本身不能
证明自动休眠是原因，应结合原生会话运行期间的读数和掉线时序判断。

原 PL 连接保持诊断实测完成 140.09 秒，8402 条状态消息、265 条质量消息，
errors=[]，未提前退出；USB devnum 一直为 16，初始 resuming 后持续 active，
runtime_suspended_time 一直为 318077 ms，运行期间未挂起、未重新枚举。
诊断以 SIGTERM 结束原生采样，native_cleanup_exit=1；因此只记“完整保持区间
未复现掉线”，不把原生退出码写成成功 0。诊断 Python 单元 ExecMainStatus=0、
Result=success、inactive，原 PL、正式发布、boot ID、采集/网页 PID 均未变。
该对照没有训练并进入选择状态，观察时间也有限，不能单凭它断定 HDMI 共存
是原因，或断言线缆、供电、驱动、模组故障已排除。当前所有本轮显示/诊断
进程已退出，正式服务继续运行，临时稳定串口 drop-in 保留。

## HDMI 同场 USB 对照及暂未恢复的设备状态（06—10）

继续采用有限期、静音、无轮椅/实体输出、无 point/compute 的诊断。观察器只
共享已核验的显示 owner，不另行下载 PL；单元、PID、命令行、状态文件、页面、
状态新鲜度及共存契约均核对。显示结束仍停止 DMA、释放缓冲区、恢复原 PL。

06 静态菜单组显示完成 160.02 秒、errors=[]，正常恢复。观察器旧报告记录
140.09 秒、3591 条消息、112 条质量消息、full_interval_completed=true；这个
字段只说明旧观察循环跑满，并不代表采样持续正常。原生红外日志最后一帧距
首帧 57.718 秒，随后不再产生新眼位消息，但进程和 USB 节点仍存在。设备编号
保持 16，运行期间挂起累计时间未增加。清理后内核报 Failed to suspend device,
error -110。观察器末尾 expected_pl_unchanged=false 来自显示先结束恢复，不能
将它解释为显示期间随意重编程或隐藏该失败字段。

因此诊断已修正：只有质量/眼位采样才能刷新新鲜度；启动超过 10 秒无采样、
采样中超过 3 秒无新数据或原生提前退出，都明确失败，不因进程存活、ready
消息或旧报告字段而算通过。显示 owner 核验 5 项与新鲜度 3 项板端测试通过。

07 视频显示没有及时接上观察器，不能计为 USB 视频共存验收。08 在 07 显示
owner 尚未退出时尝试启动，被现有锁拒绝，未启动观察器；保留失败报告，不
用它评价眼控性能。09 独立视频 owner 启动后，原版眼控初始化超时 -7，观察器
约 2.96 秒提前结束、无质量采样，full_interval_completed=false。09 随后受控
退出：errors=[]、display_halted/buffers_released/original_restored=true。

源代码确认 relative-selection 的位置、左右眼比例、距离来自 STREAM_GAZE，
但此前还额外订阅 STREAM_IMAGE_SECONDARY 并保存红外诊断帧。仅给图像订阅
条件增加 !direction_mode 的候选已在板端用现有 libusb、libcrypto、libm 和
gcc -O2 -Wall -Wextra -Werror 编译通过；未改识别、标定、停留门限或标签。
没有添加驱动/依赖、电源策略、自动重连或内核配置。此项仅是假设检验，尚未
证明红外图像负载是根因。

候选曾临时放入隔离 eye 目录，10 原 PL 组仍在初始化阶段超时 -7（约 1.70 秒，
无质量采样），没有机会检验减少图像负载的效果。用户反馈拔插完成、随后保持
拔下并提供接线照片，但只读 lsusb/sysfs 始终仍是 2104:0124、device 16，未见
新的拔出或枚举记录。照片不足以追踪眼控模组到插头的完整线缆；可能是接线
位置不一致，也可能是板端 USB 状态未刷新，当前不能确定，也不能归因于用户。

为避免未验证的修改被当作正式修复，隔离源和二进制已按备份哈希恢复：
calibration.c 为 0ae5d8664016949773aa7d8270012297f619b3df47980c5b7a5f2d36748eefc2；
is4-calibration 为 e5704d8e751801ee2223a5c8f6423005cc422a0473b83b03557b6c01e3d93fc7。
候选源码、可执行文件及 backup-eye-gaze-only-20261007-10 保留在板端私有目录，
本地 calibration.c 的一处修改保留为待验证方案，不声称它与当前板端已一致。

本机最终同组 65 项检查：64 通过、1 项板端专用库检查跳过。板端界面/安全
门控及旧诊断 62 项全部通过（53.015 秒）；更新诊断 8 项另行通过；两个原有
C 标定/方向策略程序也通过。这些不代替 USB 实测或真人准确率验收。

报告副本位于 phone_video_upload/output/eye_usb_comparison_20261007，未导出
红外图片或原始眼位记录。最后核验：正式发布哈希不变、原 guardianloop_pynq.bit
已恢复、boot ID 仍 cb00a3b7-a4c3-4f0b-b4ec-bd4302af03da；正式采集 PID 29506
和网页 PID 694 均 active，累计 NRestarts 分别为 27 和 0，未新增重启。所有本轮
诊断/显示 owner 已退出，没有重启板卡或更改开机配置；下一步先核清眼控实际
USB 数据连接，再恢复采样与候选对照，不要求在异常连接状态下反复标定。

### 用户确认拔除后的补充核验

用户进一步明确眼控已经拔下，USB Host 只剩无线网卡和 Cyton 接收器。接受此
现场确认，不再要求重复拔插或把问题归因于接线错误。只读核验仍显示 EyeChip
2104:0124、device 16，USB Hub 为 05e3:0608；未出现拔除日志。对这两个设备
分别执行带 5 秒上限的 lsusb -v，均由 timeout 以 124 退出、无输出。
e0002000.usb 中断计数在多次检查期间保持 2723272。正式服务 PID/重启计数和
boot ID 不变，SSH 使用有线接口；wlan0 的 connected/IP 读数不等于实际无线
通信已经通过验证。未发现本轮检查时的 D 状态阻塞任务。

这些证据更支持板端 USB 通信/枚举状态异常，且影响范围不只眼控，但尚不能
确定是 Hub、主控制器、驱动、电源或其他硬件原因。没有执行 USB reset、解绑
驱动、改变电源策略或重启板卡。下一步建议正常重启 Z15 并重新核验 USB 和
热点连接；按项目约束，须先取得用户对此次板卡重启的明确授权。重启会清除
此前 /run 临时串口配置，之后必须重新核验 FTDI 稳定路径及正式采集启动状态，
不得假定旧 PID、USB 编号或热点地址保持不变。

### 用户执行板卡复位后的恢复

用户随后自行复位一次。读取 boot ID 已变为
8f136697-cbea-4b20-a74f-c899978d7f3a，Linux uptime 不到一分钟，确认不是仅
重新下载 PL。旧 EyeChip 节点消失；USB 列表只剩内部 Hub、8188eu 网卡和
FTDI 接收器。FTDI 稳定路径指向 ttyUSB0，正式采集 PID 670、网页 PID 669
均 active、NRestarts=0。没有重新创建此前 /run 串口覆盖配置。带 5 秒上限的
Hub 描述符读取返回 0、2424 字节，另有非必要 debug descriptor 暂不可用提示；
不能将这些启动检查等同于眼控长时稳定性验收。

复位后 wlan0 回到板卡自建 AP。沿用已核验的网络切换/回退程序和 QqqQ 保存
配置，在新私有目录 gl-phone-recovery-20261007-e86ea2cd 临时恢复客户端模式。
DHCP 地址仍为 192.168.43.6/24；电脑绑定无线地址 192.168.43.4 访问该地址
9102 端口返回 HTTP 200，经热点 SSH 核对同一主机密钥和新 boot ID。受保护
文件哈希及正式发布保持不变，PL 读回为原 guardianloop_pynq.bit。连接确认后
撤销启动回退计时器，保留手机热点连续丢失超过 90 秒时恢复原 AP 的运行时
保护；未安装开机加载项，未启动 HDMI/眼控采样或播放声音。

下一步请用户重新插入眼控 USB，再核验新的真实枚举及初始化，之后才能继续
减少红外图像负载的隔离复测。当前不声称眼控已完全修复或新候选已验收通过。

### 重新插入后：眼位流停顿与有界恢复候选

用户确认重新插好后，EyeChip 在 1-1.2 重新枚举为 device 5。手机热点地址
192.168.43.6 保持可用；本轮管理仍通过有线 192.168.2.99。正式采集 PID 670、
网页 PID 669，均 active、NRestarts=0；Cyton 采集板尚未开启。

12 组在原 guardianloop_pynq.bit 上使用 gaze-only 候选，没有 HDMI 和额外红外
图像订阅，却在 90.567 秒失败：5389 条消息、169 条质量消息，最后采样距今
3.111 秒，Native stream silent for more than 3 seconds。cleanup exit=0，
原 PL 未变。因此减少红外图像负载并未解决这次停流，不能认定 HDMI 或红外
图像负载是唯一根因。停流后 Hub/EyeChip 描述符读取均正常，USB 中断计数
162583→163114；与复位前 Hub/EyeChip 描述符同时超时、中断不增长的情况
不同。目前只能确认原生眼位流停止，尚不能确定固件、协议或 USB 传输原因。

现有 is4-probe.c 提供超时后重新订阅 STREAM_GAZE 的机制，但 calibration.c
的相对方向采样没有使用。新的隔离候选增加 stream_liveness.h：停流 1 秒后
对同一 USB 句柄最多重新订阅一次；连续缺帧达到 3 秒则失败退出。只有实际
解码的眼位帧可刷新期限，包括眼睛不可见但设备仍在发送的帧；订阅成功或其他
消息不能把旧眼位标成新数据。未增加 USB 自动重连、重置、电源策略或内核
改动；不修改标定、分类、选择门限。界面原有过期输入撤销和失败门控保持。

现有 libusb/libcrypto/libm 上 gcc -O2 -Wall -Wextra -Werror 编译通过。
新增 C 测试验证 1 秒重试、3 秒期限、单次重试、新帧复位、时钟倒退；原方向
和标定策略 C 检查通过。本机诊断、入口和输入门控回归 29 项全部通过。
第一次以不完整模块搜索路径运行产生导入错误，纠正测试入口后重跑通过；
没有为适配测试而修改业务代码。

候选二进制 SHA256：
7b02b6e74fbc8bf103c9bf0de57647e8b054ae8a029dbd78ec4656075ca90141；
calibration.c：
b30a6c0297171e7783bf42a183964729c38583c159e08f021b38679022d4fe04；
stream_liveness.h：
c06d389f2afd4ea50431b4ea9e6b2a65412b973e3cb7f9feb026893352e49500。
构建保存在 gl-media-20261007-314e8796/eye-stream-recovery-20261007-14，
临时安装仅限 brain_eye_coexist_20261005/eye；此前 gaze-only 源和二进制保存在
backup-eye-stream-recovery-20261007-14，原旧版仍在 backup-eye-gaze-only-20261007-12。

14 原 PL 组连续 140.107 秒通过：8644 条消息、270 条质量消息、errors=[]、
full_interval_completed=true、cleanup exit=0、原 PL 不变。没有触发重新
订阅，故不能以此证明恢复机制已经在真实停流中生效，也不能声称长时稳定性
已解决。

15 静音 HDMI 视频与独立眼位观察器共存连续 140.106 秒通过：8649 条消息、
270 条质量消息、errors=[]、full_interval_completed=true、cleanup exit=0。
观察器结束时加载的是预期 eye_wifi.bit，而不是原 PL；这不是恢复失败。
随后给精确 session 下发受控 stop，显示报告 errors=[]、controlled_stop/
display_halted/buffers_released/original_restored 均 true；正式服务、boot ID
和发布哈希不变。视频使用此前准备的 10 fps 竖框缓存，实测 9.979 fps，
此组不构成全任务 16 fps 验收，也不是真人眼控准确率验收。没有触发恢复重试，
故两组有限通过仍不能证明间歇性停流根因或长时恢复效果。

12、14 和 15 的结果已复制到 phone_video_upload/output/eye_usb_comparison_20261007，
不包含红外图片或原始眼位 CSV。候选保留在隔离 eye 目录，正式代码、模型、
开机配置均未修改。完成共存试验后，沿用原私有手机入口重新启动 40 分钟有限
网页服务；通过该入口启动 play-c080f7f9 的 600 秒静音统一 HDMI 会话，有
650 秒独立恢复定时器。首次 8 秒观察窗内显示尚未就绪，后续只读核验确认
正常 playing、无终止报告，未重复启动 owner。

之后进入 home 并启动一轮眼控：板端读回 state=positioning、connected=true、
error=null、calibrated=false、control_enabled=false；先显示左右眼检测比例和
距离，等待用户坐稳并确认位置。三点标定和中/左/右各一次快速检查仍是进入
选择菜单的前置条件，不自动跳过。MI 退出、SSVEP 闪烁和物理运动均关闭，
正式采集/网页服务 PID 670/669、NRestarts=0。此处仅交还可标定界面，不记录
真人快速检查已经通过；本次显示 10 分钟后退出并恢复原 PL，不是开机安装。
