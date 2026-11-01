"""Generate the candidate handoff from recorded metrics, not handwritten scores."""
import argparse
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main(output):
    result = read(output/"results.json")
    summary = result["summary"]
    baseline = summary["offline_qr"]
    candidate = summary["causal_notch_band"]
    audit = read(output/"board_audit.json")
    paced_audit = read(output/"board_audit_paced.json")
    fast = read(output/"arm/report.json")
    paced_path = output/"arm_paced/report.json"
    paced = read(paced_path) if paced_path.is_file() else None
    lower, upper = candidate["paired_ci95"]
    source_unchanged = audit["before"]["files"] == audit["after"]["files"]
    paced_complete = paced is not None and paced_audit.get("parity_passed", False)
    paced_files_unchanged = (
        paced_audit["before"]["files"] == paced_audit["after"]["files"]
        if "after" in paced_audit else None
    )
    subject_values = [r["causal_notch_band"] for r in result["per_subject"]]
    if paced_complete:
        paced_notes = [
            f"- 按 250 Hz 实际节奏回放：墙钟 {paced['wall_compute_seconds']:.2f} 秒，进程 CPU {paced['process_cpu_seconds']:.2f} 秒；每批 p95={paced['chunk_latency_ms']['p95']:.2f} ms，p99={paced['chunk_latency_ms']['p99']:.2f} ms，最大 {paced['chunk_latency_ms']['max']:.2f} ms。",
            f"- 实际节奏下相对本批数据就绪时刻的完成延后：p95={paced['paced_completion_lateness_ms']['p95']:.2f} ms，最大={paced['paced_completion_lateness_ms']['max']:.2f} ms，最后一批={paced['paced_completion_lateness_ms']['last']:.2f} ms；超过 200 ms 更新间隔的批数={paced['completion_over_hop_200ms']}。",
            f"- 实际节奏回放 PC–ARM 预测和窗口端点也一致；滤波最大误差 {paced_audit['max_absolute_errors']['filtered']:.3g}，CCA 分数最大误差 {paced_audit['max_absolute_errors']['scores']:.3g}。",
            f"- 完整取得 {paced['trials']} 段、{paced['chunks']} 批、{paced['decisions']} 次候选；全部故障检查通过：{all(paced['fault_checks'].values())}。峰值 RSS={paced['peak_process_rss_kib']/1024:.2f} MiB。",
            "- 本次记录末尾没有持续积压，但存在短时超出更新间隔的延迟尖峰；不能声称硬实时或所有批次均满足期限。200 ms 是候选更新间隔，不是包含 2 秒分析窗的端到端延迟。"
        ]
    else:
        paced_notes = ["- **按实际节奏回放未确认完成**：SSH 连接中途被对端断开，之后两个已知地址（192.168.2.99、192.168.50.1）的 SSH/网页端口均未成功响应；未取得结果。没有重复启动、重启板卡或重启服务。不能据此判断程序完成、持续积压消除或中断原因。恢复连接后应先检查原隔离目录的 result，再决定是否重跑。"]
    lines = [
        "# O1/O2 因果 SSVEP 候选：独立受试者验证与 Z15 隔离回放",
        "",
        "## 已完成",
        "",
        "固定帽位仍为 `F3,F4,C3,C4,T7,T8,O1,O2`，本候选只读取后两路原始微伏数据。新模块 `ssvep_stream.py` 与情绪/疲劳现有处理相互独立，不读取其已滤波/量化数据、不访问 PL，也不发送控制指令。",
        "",
        "处理链：原始 O1/O2 → 减去启动首样本 → 连续 50 Hz/Q30 陷波 → 连续四阶 6–45 Hz 带通 → 500 点滚动窗 → 三谐波四目标 CCA。250 Hz 采样，每批 10 点（40 ms），每 50 点（200 ms）更新；启动或重置后舍弃 160 点并重新收满 500 点，首个候选在 660 点/2.64 秒后出现。",
        "",
        "滤波状态在批次之间保留。绝对采样序号不连续（丢包、重复、倒序）、显式断连、所选通道非有限值会清除旧候选并重新热身。平线/秩不足窗不输出频率。接口需要采集端提供展开后的绝对序号，并在超时后调用 disconnect；本次没有把它接入现有 Cyton 服务，因此不声称真实 UART 事件已接通。",
        "",
        "## 独立受试者结果",
        "",
        "数据为 [Wang2016](https://zenodo.org/records/14865172)，新增 S21–S35，15 人的原始文件均完成 Zenodo MD5 校验。与前次 S1、S9–S20 不重合；没有按本批结果调参。每人 4 个预定频率（8/10/12/14 Hz）各 6 次，共 360 个独立试次，主指标仅取每试次首个完整窗，按人配对统计。",
        "",
        f"- 原离线零相位版：{100*baseline['mean_accuracy']:.2f}%。",
        f"- 同一离线信号换成可移植 CCA：{100*summary['offline_portable']['mean_accuracy']:.2f}%。",
        f"- 因果带通、无新增陷波：{100*summary['causal_band_only']['mean_accuracy']:.2f}%。",
        f"- 最终因果陷波＋带通候选：{100*candidate['mean_accuracy']:.2f}%。",
        f"- 候选相对原离线版：{100*candidate['paired_delta']:+.2f} 个百分点；逐人 bootstrap 95% 区间 {100*lower:+.2f}～{100*upper:+.2f} 个百分点。",
        f"- 候选个体准确率范围：{100*min(subject_values):.2f}%～{100*max(subject_values):.2f}%；群体平均不保证每个人可用。",
        f"- 预先门槛（均值 ≥70%，配对 95% 下界 ≥−5 个百分点）通过：{result['board_replay_gate_passed']}。这只是进入隔离回放的门槛，不是上线控制的标准。",
        "",
        "不能把本次结果与前次不同受试者的 75.35% 相减来宣称提升。四目标是原 40 闪烁目标中的子集，不是实际只呈现四个目标的实验。原数据已施加过 50 Hz 陷波；不能凭该数据证明对 Cyton 强工频干扰的抑制效果。Wang 使用不同放大器及头顶部参考，这不是 Cyton 佩戴准确率。",
        "",
        "## Z15 ARM 数值与性能",
        "",
        "回放 S21 的 24 段带标签原始试次，共 144 秒记录；每段按数据集边界重置，不能把按目标存储的片段拼成自然连续采集。408 个重叠滚动窗口只用于数值/性能验证，不用于扩大准确率样本数。",
        "",
        f"- 加速回放：ARM 用时 {fast['wall_compute_seconds']:.2f} 秒，CPU 时间 {fast['process_cpu_seconds']:.2f} 秒；滤波 {fast['filter_seconds']:.2f} 秒，CCA {fast['cca_decode_seconds']:.2f} 秒。",
        f"- 加速回放每批 p95={fast['chunk_latency_ms']['p95']:.2f} ms，最大 {fast['chunk_latency_ms']['max']:.2f} ms；有 {fast['chunks_over_nominal_40ms']} 批超过 40 ms，不用平均速度掩盖尖峰。",
        f"- 峰值进程 RSS：{fast['peak_process_rss_kib']/1024:.2f} MiB（含 Python/NumPy/SciPy 与回放记录）。",
        f"- 已完成的加速回放 PC–ARM 预测和窗口端点一致，滤波最大误差 {audit['max_absolute_errors']['filtered']:.3g}，CCA 分数最大误差 {audit['max_absolute_errors']['scores']:.3g}，均低于预定容差。断流、重热身、非有限值和平线状态核对通过。",
        *paced_notes,
        "",
        "上述性能在 ARM CPU 上测得，没有 PL 加速。保留了现有服务运行/自动重启行为，但不是情绪、疲劳、真实接收器持续有数据时的满负载测试，也不是网页/无线/刺激屏端到端延迟保证。",
        "",
        "## 板端变动与注意事项",
        "",
        f"已完成的加速回放中，核对的现有采集代码、SQI 代码和情绪模型前后哈希不变：{source_unchanged}。本次实际节奏回放同三份文件哈希不变：{paced_files_unchanged}；包括服务 PID/状态的前后快照相同：{paced_audit.get('production_snapshot_unchanged')}。前后快照不等于连续运行监控。没有主动重启/停止服务、访问串口、加载 overlay 或更新网页状态。",
        "",
        f"加速回放隔离目录：`{audit['remote_directory']}`；实际节奏回放隔离目录：`{paced_audit['remote_directory']}`。均保留以便审计，不作为自启动服务。",
        "",
        "历史中断记录：2026-09-26 首次实际节奏回放丢失 SSH，未取回结果；那次开始前 Cyton 服务处于自动重启状态，日志显示 `TimeoutError: No complete Cyton packet for 5 seconds`。原审计保存在 `board_audit_paced_interrupted_20260926.json`，不以新结果覆盖这次失败事实。",
        "",
        "2026-09-27 用户确认通电联网后重新连接：旧隔离目录 `/home/xilinx/ssvep-causal-replay-Od3TUP/result` 为空、没有回放进程，板卡 uptime 不足一分钟，boot ID 为 `e4b255dc-109b-489f-8720-83293a1de088`。在确认无结果可回收后才重新执行一次隔离回放。本次前后快照中 Cyton 和网页均为 active/running（PID 630、559）。没有据此推断此前断连/重启原因。板卡日历时间不可靠，耗时使用 monotonic/perf_counter。",
        "",
        "## 尚未部署的边界与下一步",
        "",
        "当前输出始终 `candidate_only`、`control_enabled=false`。只做了数值/平线等硬检查，未把工程 SQI 门限当作经过验证的 SSVEP 拒绝器；该数据没有足够的无注视/非目标标签，尚未验证误触发率或置信门槛。不得据此直接驱动设备。",
        "",
        ("实际节奏回放已经完成。" if paced_complete else "先恢复板卡连接并回收实际节奏回放结果，确认延后/积压情况。")
        + "下一步可把同一候选以只读旁路/影子状态接入原始采集分支，复用真实包序号与断流通知，并把无数据、质量不合格、热身、候选频率明确区分；仍不输出控制。无需马上佩戴，可先用已有记录验证这个接口。实际控制需另行验证刺激时序、无目标拒绝和满负载下的延迟尖峰。",
        "",
        "## 复现",
        "",
        "在 `D:\\ican\\codex_project\\eeg_apps_z15` 运行：",
        "",
        "```powershell",
        "python -m unittest discover -s . -p 'test_ssvep*.py'",
        "python ssvep_causal_evaluate.py --output output/ssvep_causal_20260926",
        "python run_ssvep_causal_board_replay.py --output output/ssvep_causal_20260926",
        "python run_ssvep_causal_board_replay.py --output output/ssvep_causal_20260926 --paced",
        "python report_ssvep_causal.py --output output/ssvep_causal_20260926",
        "```",
        "",
        "原始评测和源文件哈希在 `results.json`；冻结规则在 `protocol.json`；下载校验在 `download_manifest.json`；PC/ARM 数组及测量在 `pc/`、`arm/`、`pc_paced/`、`arm_paced/`；隔离目录、前后生产快照和传输哈希在两份 `board_audit*.json`。",
    ]
    (output/"RESULTS.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    main(args.output)
