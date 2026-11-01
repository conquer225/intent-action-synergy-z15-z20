# 源码说明

`workspace/` 保留 4744 个公开源码、测试和配置文件的原始字节。路径按英文规范化；过长路径放入 `workspace/short/`。完整的原路径、存储位置、字节数与 SHA256 在[来源清单](../report/source_manifest.json)。

在仓库根目录执行 `python -X utf8 -B build/restore_workspace.py --output C:/work/intent_action_runtime`，再到恢复出的原目录阅读和运行程序。恢复目标必须尚不存在且位于仓库外。

本目录是公开源码选集。模型、系统介质、厂商 SDK、原生库与未公开的历史文件见[外部输入清单](../report/external_inputs.json)，它们不是恢复命令自动下载的内容。原文档可能引用这些输入；完整视觉和板卡工作流需先补齐对应版本。
