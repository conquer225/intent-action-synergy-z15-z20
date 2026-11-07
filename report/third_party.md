# 来源和许可范围

本公开副本保留原文件内容与已有版权声明。原始 `LICENSE`、`COPYING` 等文件采用规范化存储名，按来源清单恢复后回到原路径和大小写。

队伍自有源码尚未指定统一开源许可证。本次上传不把 MIT 或 Apache-2.0 扩展到全部代码、厂商参考、模型或数据。发布可见的源码与授予额外再分发权利是不同事项；第三方内容继续使用其原许可。

| 内容 | 来源及处理 |
| --- | --- |
| 通用 PYNQ Skill | 自行编写的工具、合成例子和提示词；官方接口及检索来源见[Skill 来源](../skill/sources.md) |
| 显示控制基础 | [Project F display_controller](https://github.com/projf/display_controller)，原声明 MIT；已有文件级声明随源码保留 |
| 浏览器流体和声谱 | [WebGL Fluid Simulation](https://github.com/PavelDoGreat/WebGL-Fluid-Simulation)、[3D Spectrogram](https://github.com/conwayjw97/3D-Spectrogram) 及 Three.js；MIT/GPL 声明与固定来源清单随所选源码保留 |
| ALIENTEK、Navigator、AMD IP 和其他 SDK | 外部厂商依赖，不在本次公共源码副本中重新授予许可；从相应官方板卡资料或工具取得匹配版本 |
| 相对深度模型 | 原工程使用 Ultralytics 模型及其 AGPL 条件；权重与运行环境不随本仓库发布 |
| EEG、录音及图像素材 | 原有数据来源及使用条件分别核对；本次没有公开原始采集、音视频和个人照片 |

来源清单记录公开文件字节身份，外部输入清单记录未发布文件的路径与摘要。第三方版权和再分发条件仍以相应原始文件及来源为准。

## 本次 PL 扩展的参考来源

| 内容 | 参考与采用方式 |
| --- | --- |
| 脑电处理顺序 | [Xsingh-Luo/fpga_eeg_rehab](https://github.com/Xsingh-Luo/fpga_eeg_rehab/tree/7b828d17c8eb51da2c19a4fbdff8a3e941593501)：阅读 SOS、CSP、滑窗、log 方差和 SVM 的 RTL 及训练流程。上游 LICENSE 含 MIT 正文及第三方附注。 |
| 空间显示分工 | [ymmz2333/fpga-orb-slam](https://github.com/ymmz2333/fpga-orb-slam)、[yilives/zynq-ultrascale-graphics](https://github.com/yilives/zynq-ultrascale-graphics)：参考几何投影及 PS/PL 职责组织。 |
| 原创实现范围 | 新增 `integrations/pl_accel` 的 HLS 核、定点数值合同、参考模型、训练导出、驱动、实时消费者、地图适配与测试由本工程独立编写。算法参考按本表注明来源。 |

外部工程的源码以只读方式研究。本次采用明确的八通道 Q8/Q28/Q14/Q12 合同、逐频带归一化及本工程模型格式，模型参数与来源随 SHA256 记录。
