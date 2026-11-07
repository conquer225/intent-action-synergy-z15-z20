# 双板 PL 计算模块

本包提供 Z15 FBCSP/SVM 和 Z20 点云/轨迹绘制的统一数值与驱动接口。

| 文件 | 职责 |
| --- | --- |
| `fixed.py`、`eeg.py` | 定点规则、模型合同、独立脑电整数参考 |
| `train.py` | CSP、特征选择、线性 SVM 与 JSON 参数导出 |
| `mapping.py`、`view.py` | 几何合同、独立整数光栅参考与观察相机 |
| `backend.py`、`metadata.py` | MMIO、缓存、DDR 所有权与 HWH 地址解析 |
| `live.py` | 单一采集源的有界消费者、复位、撤销与状态发布 |
| `hls/` | 两套可综合 HLS 核、C/RTL 测试台及固定向量 |
| `hardware/` | 原 BD 增量集成 Tcl 与 Z20 UIO 设备树片段 |

EEG 输入为 `[N,8]` 的 signed24 Q8 µV，输出六项 Q12 特征和 signed64 Q24 SVM 分数。地图输入为 XYZ/RGB 与可选轨迹，输出 RGB 帧和裁剪/可见点统计。两者通过 AXI4-Lite 管理指针，AXI 内存主端口读取参数、数据并写回结果。

新消费者输出左右手比较结果；既有 EEGNet、眼控和设备控制链各自持有原动作职责。地图渲染沿用显示所有者，默认原有模式。

完整寄存器表、训练命令、固件构建及数值记录见仓库 `report/pl_accel.md`。[术语](glossary.md)说明本包接口中的固定含义。
