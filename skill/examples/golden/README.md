# 可直接运行的数值示例

这些文件是人工构造的 synthetic fixture，用于检验比较器的接受和拒绝行为。`actual-pass.jsonl` 的后端名也明确标为样例；本例没有执行 PL。

模型文件 `model.json` 定义一个两输入、两输出的整数仿射运算，权重按输出行排列：`W=[[2,-1],[1,3]]`，偏置 `b=[0,-1]`。输入 `x=[3,2]`，每个输出等于一行权重与输入逐项相乘之和，再加该行偏置：

```text
y[0] = 2*3 + (-1)*2 + 0 = 6-2+0 = 4
y[1] = 1*3 + 3*2 + (-1) = 3+6-1 = 8
```

输入的合同是 shape `[2]`、有符号 INT32、小端、按元素连续排列。`input_le_i32.hex` 保存实际输入字节的十六进制文本 `0300000002000000`。记录的 `input_sha256` 对 `bytes.fromhex(...)` 解码后的八个字节计算，`model_sha256` 对随包 `model.json` 的实际文件字节计算。复制时保留文件字节；更换编码、缩进或换行会改变模型文件摘要。

`reference.jsonl` 的预期向量固定为手算值 `[4,8]`。通过样例为 `[4,8]`，故障样例为 `[4,7]`。二者最高值都在索引 1，只有比较全部输出才能发现错误。

在技能包根目录运行：

```sh
python scripts/compare_golden.py examples/golden/reference.jsonl examples/golden/actual-pass.jsonl
python scripts/compare_golden.py examples/golden/reference.jsonl examples/golden/actual-bad.jsonl
```

预期返回码依次为 `0`、`1`；第二条输出第 1 个索引的 expected=8、actual=7。换到本题时从真正执行的两端分别导出记录，摘要从实际输入计算，不能复制本例的身份字段充当硬件证据。
