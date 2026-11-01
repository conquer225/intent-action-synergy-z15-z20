---
name: pynq-portable-workflow
description: "检查 PYNQ bit/HWH 交付、核对 PS/PL 同输入数值、排查板卡重连与过期结果。用于已有硬件设计的部署检查和协作调试；镜像制作、未知板卡引脚设计和直接运动控制另行处理。"
---

# PYNQ 可迁移验证工作流

根据当前问题选择工作流，只读取需要的参考文件：

| 当前任务 | 使用材料 |
| --- | --- |
| 自定义 overlay 换版本、换板或加载失败 | [PYNQ 检查](references/pynq-bringup.md)和[加载审阅提示词](prompts/overlay-review.md) |
| PS/PL 输出不同、量化版本变化或加速比不明 | [黄金参考](references/integer-reference.md)和[整数定位提示词](prompts/integer-debug.md) |
| 断电后失联、DHCP 改变、切模式或重连仍显示旧结果 | [会话恢复](references/session-recovery.md)和[恢复提示词](prompts/session-recovery.md) |
| 依据综合/实现和运行日志选择优化点 | [资源及时延提示词](prompts/report-analysis.md) |

先确定实际器件与封装、软件环境、输入来源、当前资源所有者，以及能观察结果的接口。板卡名、IP 名称、网络地址、维数和超时均来自本次材料；不要从示例复制成现场事实。只有 Zynq `.bit/.hwh` 静态路径在本包作了文件级验证；其他 PYNQ 平台按实际交付格式选择对应检查器。

用 `scripts/check_overlay.py MANIFEST --part ACTUAL_PART`检查 bit/HWH 摘要、器件与封装、文件配对及所需 IP。清单由可信构建记录产生；重新登记损坏文件的摘要会失去原校验基线。工具不会加载 PL。HWH 解析及 IP 存在也不确认引脚、电压、速度等级、时钟或驱动兼容。

用 `scripts/compare_golden.py REFERENCE ACTUAL`比较同一输入、模型和量化版本的全部数值。整数默认逐值精确相等；浮点容差必须有算法误差依据。保留输入与模型摘要、原始输出、实际后端及计时范围。整型一致、教师一致、真实标签准确率分别记录。

用 `scripts/check_session_trace.py TRACE --ttl-ms VALUE`审计日志中接收决定和显示状态。它检查会话、模式版本、递增序号、收到结果后的显示期限及无效状态清空；输入时已经过期的判断需要生产端另行记录。该格式是离线审计格式，接现有协议时转换日志字段，保留原协议。

出现不一致时先保存失败输入、原日志和当前状态；从第一个发生差异的层检查。每次只改变一个可验证因素。DMA 超时后先查硬件是否仍拥有内存，停止/复位经确认后再释放；重连清除旧结果，动作权限按原产品规则重新建立。

交付输出应包含：问题与适用范围、实际命令与配置、通过和失败记录、来源、未完成的验证。使用 [运行记录模板](templates/run-record.example.json)。本包的测试和示例是离线证据；实际板卡、网络、屏幕和执行端结果需要现场记录。可参考[失败来源索引](examples/z15-z20/README.md)，通用流程不依赖该案例。
