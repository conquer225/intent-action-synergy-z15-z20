# GuardianLoop 安卓手机网页

## 当前状态

2026-10-03：用户授权后已备份并上线到 Z15，网页与接口验收通过。
发布为 `guardianloop-fixed8-mobile-web-20261003`，仅重启了 `guardianloop-web.service`。
不停止采集服务，不修改模型、通道、信号门限、设备树、PL 或 SD 启动镜像。

## 上线后的使用方式

1. 安卓手机连接 `GuardianLoop-Z15`，无互联网提示时保持连接。
2. 浏览器打开 `http://192.168.50.1:9102/mobile`。
3. 如需快捷入口，可使用浏览器“添加到主屏幕”；这只是网页快捷方式，不是原生 APK 或可离线预测的 PWA。
4. 保持页面在前台；后台、锁屏、网络中断时隐藏旧结果，返回后重新读取。

电脑不参与运行。Z15 上既有采集及计算服务负责处理，手机只负责显示和交互提示。
本次手机页不提高模型准确率，也不改变 ARM/PL 分工。

## 功能与边界

- 情绪相关估计：显示 GAMEEMO 游戏条件类别，不将其宣称为使用者真实情绪。
- 疲劳：显示既有 ARM 模型结果及校准/质量状态，不替代安全判断。
- SSVEP：显示 O1/O2 的被动频率候选，不把候选当作已确认注视选择；本版不提供手机闪烁刺激。
- 运动想象：查看当前提示试次，进入既有 `/mi-cued` 虚拟手页面；没有真实外设控制。
- 显示固定八通道质量/降权状态；无及时输入时不保留预测结果。
- 页面不上传数据到云、不保存脑电到手机，不提供后台监控或系统通知。

固定帽位仍为 `F3,F4,C3,C4,T7,T8,O1,O2`，参考 SRB2，偏置 BIAS。
手机 SSVEP 刺激刷新率适配及光学/真人识别验收不在本次完成范围。

## 文件

- `pynq_guardianloop/guardianloop_web.py`：新增 `/mobile`、`/mobile/`、`/mobile.js` 三条静态路由，主网页增加手机入口。
- `pynq_guardianloop/mobile.html`：小屏布局及功能边界。
- `pynq_guardianloop/mobile.js`：既有接口的只读轮询、超时、前后台与旧结果撤销。
- `pynq_guardianloop/test_mobile_web.py`：路由、MIME、禁用缓存、无状态文件写入。
- `pynq_guardianloop/test_mobile_browser.cjs`：虚拟 DOM 状态机回归。
- `eeg_apps_z15/output/mobile_web_20261003/mobile_preview.jpg`：本地无采集输入预览，不是安卓实体设备或板端实时截图。

移动首页只读 `/api/status`、`/api/ssvep-shadow`、`/api/mi-cue`，请求之间不重叠。
完成一轮后约 1 秒再读，单接口 1.8 秒超时，3 秒无及时回复撤销结果。
不发送试次开始/停止命令，不给既有运动想象试次发送保持活动心跳。

## 已验证

33 项 Python 接口/回归测试通过；手机页虚拟 DOM 测试通过有效结果、过期、回放、通道错误、质量拒绝、断网、后台和迟到回复分支。
本地浏览器 360 像素竖屏及 640 像素横屏无水平溢出，主按钮 48 像素，控制台无错误；运动想象入口导航正常。
测试未启动闪烁、真实外设或板卡采集。

复现（PowerShell，在 `D:\ican\codex_project`）：

```powershell
$env:PYTHONPATH='D:\ican\codex_project\pynq_guardianloop;D:\ican\codex_project\eeg_apps_z15'
& 'D:\ican\codex_project\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 -m unittest test_mobile_web test_seed_shadow_web test_mi_formal_entry test_ssvep_free test_guardianloop_startup
& 'C:\Program Files\nodejs\node.exe' pynq_guardianloop\test_mobile_browser.cjs
```

## 上线验收记录

- 69 个基线文件哈希匹配，运动想象、SSVEP 提示、自由选择和原始记录均为 idle。
- 当前启动 ID 为 `854c1e44-8666-49fc-a059-66fa4288d945`；部署未重启板卡。
- 采集进程 PID `695`，部署前后保持 active、NRestarts=0。
- 只替换 `guardianloop_web.py`、`release_manifest.json`，新增 `mobile.html`、`mobile.js`。
- 模型、采集/启动服务文件、PL `.bit/.hwh`、SD 启动文件及启动自检记录未变。
- 12 个页面/接口返回 HTTP 200；手机页和脚本 no-store，脚本响应哈希与安装文件一致。
- 电脑直接经 Z15 热点请求 `/mobile` 返回 HTTP 200。
- 内置浏览器访问未成功，未获得板端实页截图；真实安卓浏览器验收仍待用户完成。
- 网页显示“新清单待下次开机核对”是正常状态：本次没有运行会加载 PL 的启动自检，也没有安排重启。

证据：`eeg_apps_z15/output/mobile_web_deploy_20261003_223346/result.json`。
原始网页及清单备份同时保留在该目录的 `backup/` 和板端 `/home/xilinx/mobile-web-TmpErj/backup/`。
冻结恢复包为该目录的 `guardianloop_mobile_web_recovery_verified_20261003.zip`：48 个运行文件按新清单核对，57 个压缩条目逐项核对；排除凭据、真实脑电及 Python 缓存。SHA256：`76d094d91feade0186dfed8ae00c8ea110b2bcc681245f8f86a30054dd7689ed`。它包含原正式 bit/HWH 作为恢复材料，本次未重新加载 PL。

## 部署流程与后续检查

1. 只读核对当前板卡启动 ID、正式文件哈希和正在进行的试次，避免覆盖他人修改或中断试次。
2. 备份现有网页及发布清单，生成新清单；原正式发布 `guardianloop-fixed8-ssvep-study-20261003` 保留。
3. 仅安装三个网页文件及配套清单、重启网页服务；采集 PID、模型、PL、启动服务保持不变。
4. 核对手机页、现有接口、服务状态及保护文件哈希；失败则回退网页和清单、重启网页服务。
5. 【待用户确认】用真实安卓手机打开页面确认可读、可触控、断网/后台会撤销旧结果。

交付压缩包是网页更新材料，不是 SD 镜像或完整 FPGA 工程；未经本次上线核对不要用它替换板上其他文件。
