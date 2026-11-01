# 会话轨迹示例

这是使用同一接收端单调时钟构造的 synthetic fixture，单位毫秒，TTL 为 100 ms。它演示模式切换、断连重连、旧连接结果拒绝及过期显示清空；没有连接真实设备。

`pass.jsonl` 中 A 会话首先接受一个结果，切到新 epoch 后拒绝旧模式结果；断连后建立 B 会话，再拒绝迟到的 A 结果。B 的新结果显示后，到达接收后第 100 ms 时清空显示。中间心跳不刷新分类期限。

`bad-old-session.jsonl` 只把迟到的 A 结果的 `accepted` 改为 `true`，模拟程序错误接受旧连接数据。工具应返回 `accepted_old_session`。每行字段见[轨迹合同](../../references/session-recovery.md)。

在技能包根目录运行：

```sh
python scripts/check_session_trace.py examples/session/pass.jsonl --ttl-ms 100
python scripts/check_session_trace.py examples/session/bad-old-session.jsonl --ttl-ms 100
```

预期返回码依次为 `0`、`1`。接入自己的工程时在实际接收决定和显示观察点生成日志；本例预先写出的轨迹只能检验工具，不能验收另一个程序。
