# PYNQ 与双板协作技能包

本包用于 PYNQ 自定义 overlay 的交付检查、PS/PL 数值核对，以及多设备重连和旧结果排查。它从 Z15＋Z20 联动工程的器件适配、显示资源管理、整数推理和断电恢复记录中提炼，板卡、IP 名称、网络地址、模型和时限均由使用者填写。

主入口是 [SKILL.md](SKILL.md)。普通队伍可以直接按下面的工作流操作；大模型可读取该入口及对应参考文件。整个 `skill/` 目录可复制到其他工程，不依赖原工程的 Python 包、脑电模型、设备地址或执行机构。

## 内容与适用范围

| 工作流 | 适用场景与用法 | 已验证的效果与来源 | 失效条件 |
| --- | --- | --- | --- |
| [PYNQ 加载前检查与 DMA 排查](references/pynq-bringup.md) | 有完整 Vivado `.bit/.hwh`，需要交付或换板；填写清单后运行 `check_overlay.py` | 本包测试覆盖器件封装不符、HWH 错配、摘要损坏、缺少 IP；来源为本队 CLG400/CLG484 目标混淆、固件摘要漏更新及 DMA 超时处理观察 | 清单来源不可信、载荷格式不同或板级电气/DDR/时钟未核对时，静态通过不能作为上板许可；DMA 步骤需要实际寄存器和波形 |
| [同输入黄金参考与耗时核对](references/integer-reference.md) | FPGA/HLS 算法、量化模型、滤波器等有独立软件参考；导出 JSONL 后运行 `compare_golden.py` | 可发现类别未变但某个输出错一位、输入/模型/量化版本不一致；本队历史记录有 20/180/40 维三任务真实 PL 整数核对 | 原始输入、参考算法或模型身份不完整时，不能建立同输入结论；数值一致性不代替真实标签准确率 |
| [板卡与会话恢复](references/session-recovery.md) | 断电后失联、地址变化、模式切换后旧结果残留；按层恢复并用 `check_session_trace.py` 审计日志 | 本包用例能检出旧会话/旧模式被接受、重复序号、结果过期仍显示；本队历史恢复后有 10.2 秒正常心跳记录 | 日志缺失、跨设备时钟混用、未观察实际显示时不能据此判断整机；通信恢复与机构就绪分别验收 |

每项的前置条件、输入输出、步骤、失败入口和复用办法都在对应参考文件中。[踩坑清单](references/pitfalls.md)按触发条件给出排查步骤和停止条件。[Z15/Z20 案例](examples/z15-z20/README.md)说明这些流程来自哪些实际失败或观察。

## 提示词、模板与清单

下面材料随三个工作流使用。提示词按文件内的输入栏补齐真实材料后提交给模型；JSON 模板复制为本题配置后填写。四份提示词是本次新整理的工作流，未单独测量跨模型稳定成功率；已验证的基础来自对应脚本、软件回归和历史观察。

| 材料 | 用法、来源与验证范围 | 失效条件 |
| --- | --- | --- |
| [加载审阅提示词](prompts/overlay-review.md) | 审阅板型、构建身份和所有权；E01/E02/E03；脚本测试能拒绝错封装、错摘要和缺 IP | 缺实物身份、构建清单或当前所有者 |
| [数值定位提示词](prompts/integer-debug.md) | 导入两份输出，按第一个差异追查；E03/E04；比较器测试检出单值错误和身份变化 | 缺独立参考、原输入或量化合同 |
| [会话恢复提示词](prompts/session-recovery.md) | 按断层给最小恢复操作及观察；E05/E06/E07；软件用例覆盖旧结果和过期显示 | 目标身份、时钟或实际显示日志不明 |
| [资源与时延提示词](prompts/report-analysis.md) | 对齐构建阶段和计时范围后分析划分；E04/E08；来源保留调用较慢样本与非零退出记录 | 无匹配报告或可比测量，不能下达标结论 |
| [板卡模板](templates/board-profile.example.json) | 登记器件、封装、系统和资源所有者；E01/E03；本次检查 JSON 格式与流程字段 | 未填写字段或未核对实物时只是空记录 |
| [固件清单模板](templates/overlay-manifest.example.json) | 在可信构建完成时填入配套文件和摘要；E01/E02；同一格式用于工具测试及真实归档预检 | 全零摘要和占位值必须替换，事后重写基线会丢失校验依据 |
| [运行记录模板](templates/run-record.example.json) | 记录命令、失败、计时范围及各层验收；E04/E05/E08；本次检查 JSON 格式，实际执行证据见验证目录 | 无原始日志或把未测项填成通过 |
| [踩坑清单](references/pitfalls.md) | 按触发条件选择排查项，查原始 E01–E08 记录；软件用例和历史记录分别注明 | 未命中触发条件时应重新定位，不能按旧故障套结论 |

## 先在普通电脑运行

三个检查工具仅用 Python 标准库，采用 Python 3.8 兼容语法；本次实际运行环境见验证记录，其他 Python 版本需在本机复跑。进入本目录后执行：

```sh
python -m unittest discover -s tests -v
python scripts/compare_golden.py examples/golden/reference.jsonl examples/golden/actual-pass.jsonl
python scripts/check_session_trace.py examples/session/pass.jsonl --ttl-ms 100
```

下面两条是故障示例，预期返回码为 `1`，输出 `passed: false`：

```sh
python scripts/compare_golden.py examples/golden/reference.jsonl examples/golden/actual-bad.jsonl
python scripts/check_session_trace.py examples/session/bad-old-session.jsonl --ttl-ms 100
```

`0` 表示本次文件检查通过，`1` 表示发现约定不一致，`2` 表示输入缺失、格式错误或参数无效。工具输出 JSON，可重定向到检查记录。所有输出都标有 `board_executed: false`；这些命令在电脑检查文件，不连接板卡。

## 用到自己的题目

先在 [板卡信息模板](templates/board-profile.example.json)填写实际器件、封装、系统、PYNQ 版本和资源所有者。从同一可信构建导出 bit/HWH，按 [清单模板](templates/overlay-manifest.example.json)记录路径、摘要及实际使用的 IP。清单中的全零摘要是待填写字段，模板本身不是一份已通过的交付清单。

```sh
python scripts/check_overlay.py /path/to/release/manifest.json --part ACTUAL_DEVICE_PACKAGE
```

`ACTUAL_DEVICE_PACKAGE` 换成实物记录的器件加封装，可带 `xc` 前缀，不带速度等级；速度等级和板修仍在板卡记录中单独核对。Windows 用 `Get-FileHash -Algorithm SHA256`，Linux 用 `sha256sum`取得文件摘要。全部路径相对于清单所在目录，bit/HWH 必须同目录同名。

## 与大模型协作

可以将 [加载检查提示词](prompts/overlay-review.md)、[数值定位提示词](prompts/integer-debug.md)、[会话恢复提示词](prompts/session-recovery.md)或[资源与时延分析提示词](prompts/report-analysis.md)连同真实材料交给模型。提示词列出了输入、输出和必须停止下结论的条件。它们是本次依据工程经验新整理的模板，验证依据是对应脚本和工程记录，尚未测量跨模型成功率。

如需作为 Agent Skill 使用，将整个目录复制并命名为 `pynq-portable-workflow`，放入所用工具的本地技能目录，保持子目录结构，再按该工具的加载规则调用。人工使用直接运行本包文件即可。

## 证据与开源来源

[观察记录](evidence/project_observations.json)保存失败或观察、处理方式、结果范围和来源；[源码索引](evidence/source_index.json)保存核对文件的 SHA256。[阅读范围](evidence/review_scope.md)说明工程覆盖情况。[验证记录](verification/README.md)列出本次实际执行的命令、运行环境和结果。

开源依据与许可证见 [sources.md](sources.md)。包内检查工具和提示词依据本次需求编写，没有随包复制上游代码、厂商固件、模型或私有网络配置。既有工程结果与本次离线检查分开记录；这次整理未开展新的板卡或机械测试。内容依据源码、归档日志及公开文档，由 AI 辅助整理和编写。
