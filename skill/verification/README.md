# 本次验证记录

检查日期：2026-11-01。运行环境：Windows 11、Python 3.14.7；原工程相关回归使用 NumPy 2.5.2。三个交付工具及包内测试只依赖标准库。Python 3.8 语法解析通过，实际运行只覆盖上述 Python 版本。

| 验证项 | 实际结果 | 原始记录与适用范围 |
| --- | --- | --- |
| 新工具的公开 CLI | 14 项测试通过，含多组故障子用例 | [完整日志](portable-tests.txt)；合成 fixture，不接板 |
| 原工程相关回归 | 12 项测试通过 | [完整日志](project-tests.txt)；整数参考、DMA 所有权、板型拒绝、结果缓存和视频；含本机 socketpair，未访问板卡 |
| 随包正负例 | 四条命令分别返回 0、1、0、1，与预期一致 | [命令与 JSON](cli-examples.json)；两份通过、两份预期失败 |
| 真实归档 bit/HWH | Z15 目标通过，改填 Z20 CLG400 被拒绝；原 ZIP CRC、质量清单摘要一致 | [清单和输出](archived-overlay.json)；只读取归档，不加载 PL |
| 源码/摘录/语法 | 45 份来源摘要、34 个历史 JSON 字段逐项核对；4 个 Python 文件编译与 3.8 语法解析通过，样例输入/模型摘要一致 | [检查结果](source-and-syntax.json) |
| Skill 元数据 | 本机 skill-creator 的 quick_validate.py 返回 0，输出 Skill is valid! | [汇总](results.json)；只检查技能元数据与脚手架格式 |
| 独立复制 | 临时目录名称含空格，移除 PYTHONPATH、使用 Python 隔离模式，14 项测试和四条正负例均符合预期 | [独立日志](isolated-tests.txt)及[输入摘要](isolation-check.json)；不依赖原工程工作目录 |
| 文档与文件 | 本地链接、UTF-8、JSON/JSONL、代码围栏及交付目录内容检查 | [文件检查](file-checks.json)；最终摘要见包根的 sha256sums.txt |

机器可读汇总在 [results.json](results.json)。压缩包另行做 CRC、逐文件摘要和独立解包检查，其记录放在压缩包旁；本目录记录的是包内工具和材料检查。

## 复跑包内测试

在技能包根目录运行：

```sh
python -m unittest discover -s tests -v
python scripts/compare_golden.py examples/golden/reference.jsonl examples/golden/actual-pass.jsonl
python scripts/compare_golden.py examples/golden/reference.jsonl examples/golden/actual-bad.jsonl
python scripts/check_session_trace.py examples/session/pass.jsonl --ttl-ms 100
python scripts/check_session_trace.py examples/session/bad-old-session.jsonl --ttl-ms 100
```

两条故障命令返回 1 是预期结果，不能将它们改成通过。测试覆盖器件封装、HWH 目标、摘要、IP、路径、载荷截断，输入/模型/量化/来源身份、全输出数值、大整数精度，会话/模式/序号、断连、无效显示、过期和时间倒退。位流测试中的最小二进制是解析用假数据，不可下载到 PL。

## 原工程回归的复跑范围

原工程在 `integrations/z20_compute` 执行以下脚本；它需要原工程文件及依赖，普通队伍使用本包时无需执行：

```python
import unittest

suite = unittest.TestSuite()
for name in ("test_npu.py", "test_backend.py", "test_board_target.py",
             "test_link.py", "test_video.py"):
    suite.addTests(unittest.defaultTestLoader.discover("tests", pattern=name))
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
```

真实固件检查使用原工程归档 `integrations/z20_compute/artifacts/z15-motion-firmware-candidate-20261028.zip`。先固定 ZIP 摘要，再核对质量清单、提取同名 bit/HWH 至临时目录，运行加载前检查器。归档文件未随技能包分发；测试日志保存了原摘要及实际清单。

## 开发与证据边界

新工具按公开 CLI 做红绿测试：缺少工具时入口测试失败，再实现；HWH 目标缺检查时出现期望拒绝却返回 0，补检查后通过；布尔值冒充 epoch/sequence 的显示用例也先失败再修复。最终通过日志如上，开发过程的描述不替代当前结果。

本次未执行 Vivado 综合/实现、PYNQ 镜像部署、真实 DMA 传输、板间无线恢复、HDMI 外观、真人分类准确率或机械动作验收。历史上板结果按原文件范围保存在[案例](../examples/z15-z20/README.md)。尚未测量其他板卡、其他 Python 运行版本或多种大模型上的提示词成功率；换板/换题后按模板重新建立这些记录。
