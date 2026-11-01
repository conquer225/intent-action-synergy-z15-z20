# 黄金参考示例

本目录保留可手算小网络的输入、模型及预期输出，用于验证比较器。`reference.jsonl` 对应三个原始输出 `[3,125,-3]`；`actual_pass.jsonl` 是匹配结果，`actual_bad.jsonl` 保持类别但改动一个数值。

从仓库根目录运行：

```sh
python -X utf8 -B skill/scripts/compare_golden.py data/reference.jsonl data/actual_pass.jsonl
python -X utf8 -B skill/scripts/compare_golden.py data/reference.jsonl data/actual_bad.jsonl
```

预期分别返回 0 和 1。这里的合成例子不是实际板测输出或分类准确率数据。原模型、录音、图像和输入数组不随本公开版发布，所需文件身份见[外部输入清单](../report/external_inputs.json)。
