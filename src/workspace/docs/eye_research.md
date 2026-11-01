# 眼控参考与实现对应

2026-09-25 新增：[OV5640 可行性科研核查](ov5640_research_feasibility_20260925.md)。核对普通 RGB 的 MPIIGaze / GazeCapture、引用 OV5640 模组的 NIR 驾驶注视论文及梯度眼中心定位方法；支持继续评估 OV5640，不代表当前 Z15 固件已通过真人验收。

检索与核对日期：2026-09-23。用户提到的 2024 易灵思项目已找到高度吻合的原作者文章；用户原先阅读的论文名称不详，下面两篇是本次重新检索的相关论文，不能说成用户原先看的就是它们。

## 2024 易灵思作品

forever_00_，《2024嵌入式FPGA竞赛国特-最佳创意奖-红外瞳孔追踪系统（教学向）》，文章显示最后修改于 2025-03-04。

- 原作者文章：https://blog.csdn.net/forever_00_/article/details/145709587
- 作者链接的演示：https://www.bilibili.com/video/BV1mQzfYSEV3
- 作者自述为南京邮电大学学生；获奖称谓来自作者文章，本次未另查官方获奖名单。
- 硬件：Ti60F100、VS-SC130GS、红外窄带滤片、红外补光、眼球模型和云台。
- 处理：亮度阈值 → 两个亮斑区域 → 附近暗瞳区域 → 边界与参考位置比较 → 八方向输出 → HDMI 叠框。还有双眼丢失/重现计时、补光 PWM 调节。

已阅读文章展示的 `binarization`、`VIP_multi_target_detect`、`VIP_multi_target_detect_black`、`VIP_Video_add_rectangular`、`rec_rst`、`cnt_all` 说明与代码。借鉴的是区域限定、每帧锁存、有效标志、参考位置校准和时间状态机的设计。未直接复制这些模块。该文涉及红外反射亮斑，不能据此承诺普通彩色 OV5640 同样效果；原文对“暗瞳效应”的表述也不作为光学定律引用。

移植边界：Efinity 的 PLL、存储 IP 和 SC130GS 接口不能用于 Z15；本工程使用 Vivado/XPM、OV5640 RGB565 和板卡 P2 约束。文章中的矩形边界减法若直接用于小分辨率需处理无符号下溢；帧同步的极性也应以采集端为准。文章页面标注 CC BY-SA 4.0，其他被引用源码的权利需分别核对。

## PuRe

Thiago Santini, Wolfgang Fuhl, Enkelejda Kasneci. *PuRe: Robust pupil detection for real-time pervasive eye tracking*. Computer Vision and Image Understanding, 2018. DOI: https://doi.org/10.1016/j.cviu.2018.02.002 。预印本 2017：https://arxiv.org/abs/1712.08900 。

已下载 11 页原文，核对摘要、方法 §3（pp3–4）及实验 §4 的主要评估定义（p5）。方法包括归一化、Canny 边缘、曲线段筛选、椭圆拟合、条件边缘段合并；候选置信度结合椭圆长短轴比例、边缘角度分布和轮廓内外对比度。论文要求评估“没有瞳孔”的图像，而不是给每幅图强制输出位置。

本工程采用 INVALID、面积/对比度/形状拒识、校准样本稳定性检查，并把空白、全黑、畸形帧、闭眼条纹、断流列入测试。当前 `Q` 字段只是 ROI 灰度极差，**不是 PuRe 的置信度**。当前 RTL 不包含 Canny、椭圆拟合、轮廓合并，不能写成 PuRe 的 FPGA 复现。论文的头戴式近眼图像、检测率与运行帧率不代表普通 OV5640 的实测表现。

## ElSe

Wolfgang Fuhl, Thiago C. Santini, Thomas Kübler, Enkelejda Kasneci. *ElSe: Ellipse Selection for Robust Pupil Detection in Real-World Environments*. ETRA 2016. DOI: https://doi.org/10.1145/2857491.2857505 。预印本 2015：https://arxiv.org/abs/1511.06575 。

已下载 9 页原文，核对摘要与 §2（pp2–4）。主路径筛选边缘、去掉近直线结构、拟合并评估椭圆；评估考虑大小、形状、内部比外部更暗。找不到合格轮廓时，使用保留暗区域的降采样、面积差和均值滤波进行粗定位，再回原图细化。

当前硬件使用矩形包围框的宽高与暗区面积作低成本拒识，不等价于论文的椭圆筛选。阈值和比例是本工程初始参数，需用本机相机图像验证；没有照搬论文的检测率。若实拍发现睫毛/镜片反光让整块暗区质心漂移，下一步应先加入连通区域筛选或边缘候选评分，并用相同实拍序列比较误检率。

## 其他代码参考

- [GazeTracking](https://github.com/antoinelame/GazeTracking)，MIT，commit `fce71359acd5ce6843630eaf3b85558a734b0dfe`。阅读 `pupil.py` 的滤波、腐蚀、阈值、轮廓矩质心以及 `gaze_tracking.py` 的方向比值。只参考思路；没有移植其 dlib 人脸定位或模型。
- [Project F display_controller](https://github.com/projf/display_controller)，MIT，commit `dafbe3385749da4ae2100bba2945350ace7ec04e`。实际复用 DVI/TMDS 编码和串化模块，见根目录 `THIRD_PARTY.md`。
- 正点原子本地 OV5640、HDMI、UART 例程是硬件接口依据；寄存器配置表有实际改编，见同一版权清单。

## 当前适用范围

当前 v2 使用固定头部、固定摄像头、手动双眼 ROI；要求均匀可见光与清晰对焦。设计目标为左/中/右及拒识、左右停留确认，尚未完成真人验收。允许镜像方向，但每次上电/更改 ROI 都要重新校准。普通彩色相机对深色虹膜可能只分出虹膜与眼白，无法稳定分开瞳孔和虹膜，此时输出只是暗区位置，不能当作医学瞳孔测量。自动人脸定位、自由头动、全视野跟踪和八方向不属于本版已实现能力。

2026-09-25 重新核对原作者文章并分析用户实拍：当前明暗统计会受阴影、镜框和背景影响，“有效”不能等同于人眼检测成功。详见 [实拍问题与参考方案对照](eye_failure_analysis_20260925.md)。
