# 固定八通道MI五任务隔离接入

这是左右手实验候选的工程接入，**不是模型晋升、准确率提升或正式9102升级**。Cyton可保持关闭，已有156秒台架文件足够复现本轮负载；禁止用台架分类结果报告人类MI准确率。固定CH1–CH8为F3,F4,C3,C4,T7,T8,O1,O2，所有控制/生产资格标志false。

2026-10-02：三条件同场验收及最终文件/进程保护检查已通过，证据见`output/mi_multitask_20261002_retry8/RESULTS.md`、`VERIFICATION.json`、`FINAL_PROTECTION.json`。自动验收进程均已退出，以下为手动复现说明，不代表候选网页仍在运行。

## 分工

现有ARM采集主循环解析33字节包并把计数及逐样本包序号交给可选MI适配器；50样本批使用相同float64乘法转换为原始µV。MI不打开第二个串口，采用最多两个待处理批、一个有界桥接线程和独立ARM计算进程，避免模型/网页与采集主循环共享解释器。丢包、格式异常、最老样本过期、队列溢出或断流撤销候选并重新热身，不能把未知通道/标签补造为训练输入。部分批复位有同步保护，未完整的尾批不送推理。可信Pipe响应最多等待500ms，工作进程失联后撤销缓存、停用该候选，需重新启动候选才能恢复；不是自动修复损坏模型。

MI继续使用八路CAR→有状态50Hz/1–45Hz→8–30Hz→500样本热身→提示后0.5–2.5秒完整窗口→原硬SQI→原实验EEGNet。休息不推理；结果不按提示强制。模型在ARM上运行，PC浏览器只展示。PL/启动镜像/驱动没有改变。

主循环默认不加载MI模块，不启用新端口。只有同时指定`--mi-experimental-model`及`--allow-experimental-mi`才启用；`--mi-source`明确live/replay。live是采集来源标识，不代表真实效果或资格通过。

隔离网页`/`提供五任务状态及`/mi-cued`入口；`/api/multitask`显示原任务摘要与MI状态，旧状态按时效屏蔽。摘要不重复传完整质量数组，正式质量网页不变。所有EEG只能由可信Python采集适配器输入，没有网页上传EEG/伪造结果API。默认127.0.0.1，未开放板卡公网端口。候选HTTP使用单个请求线程、连接读入限时0.5秒。MI硬质量判定只计算原门控用到的p99/平线/裁剪三项，数值及门限与原完整SQI相同；未删质量门控。

## 板端手动回放（不是正式服务启动）

在本轮验收报告给出的私有stage中，用已有PYNQ Python运行。`manual_replay`必须是尚不存在的新目录，每次回放156秒，结束后撤销并关闭候选网页。下面不打开USB、不启用ESP32、不操作PL；主/候选输出均隔离并标记replay。

```bash
cd /home/xilinx/mi-multitask-GCRaw9
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python3 soak_service_replay.py --input bench_input.npz --input-kind recorded --seconds 156 --filter-backend arm --output manual_replay --mi-experimental-model experimental_eegnet.npz --allow-experimental-mi --mi-web-port 9104 --volatile-primary-dir /dev/shm/gl_mi_manual_primary --volatile-shadow-dir /dev/shm/gl_mi_manual_shadow
```

两个`/dev/shm`目录也必须未存在；不要删除未知目录来强行复用命令。再复现时自行换三个输出目录名。该命令无自动提示，与验收脚本的自动HTTP提示不同。

需要从电脑打开时，可在另一个终端建立仅展示用转发，不把计算移到电脑：

```powershell
ssh -N -L 9104:127.0.0.1:9104 xilinx@192.168.2.99
```

访问`http://127.0.0.1:9104/`，进入MI候选页。连接断开/文件结束会清空显示；这不是永久网页/开机服务部署。本轮自动验收结束后不留候选进程，正式9102仍运行原版本。

## 自动同场验收复现

```powershell
& 'D:\ican\codex_project\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 'D:\ican\codex_project\eeg_apps_z15\run_mi_multitask.py' --output 'D:\ican\codex_project\eeg_apps_z15\output\mi_multitask_reproduction'
```

只新建板端stage，原服务不停、不重启；这个输出目录必须未存在。三条件为156秒MI关闭基线、156秒五任务、156秒输入计划中34000样本暂停1.2秒/37000包终止故障。自动HTTP提示只用于软件验收，不是浏览器光学呈现或人类标签。

原四任务每次实际数学调用被捕获并在PC重算，MI工作进程独立捕获滤波/模型调用，使用独立的负编号滤波实例和`miw_`数组前缀，结束后合并复核；不是只验证父进程。回放提示在warmup完成后开始，不使用预测标签挑提示。预测负载、质量拒绝、恢复与资源分别报告。历史改善关口失败仍然有效，不能把数值/耗时通过改称模型精度通过。CPU及墙钟包含回放专用的子进程数值文件导出（最大等20秒），不能拿它们作为纯推理耗时或统计提速证明；正常候选不启用该导出。

## 正式接入尚未做

未修改`guardianloop-cyton.service`、正式9102网页、SD启动文件、设备树或PL。后续是否正式启用实验入口须明确决定并保留回退；真实MI输入和跨设备有效性仍需后续佩戴验证，本轮不要求佩戴。

后续更新（2026-10-02）：用户另行授权的默认关闭正式入口已完成，见`MI_FORMAL_ENTRY_README.md`和`output/mi_formal_entry_20261002/RESULTS.md`。上文“三条件同场验收”仍描述此前隔离阶段，不是正式MI开启验收；现有正式入口默认关闭，PL/启动镜像不变。
