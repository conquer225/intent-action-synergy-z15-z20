"""Write the runtime handoff from machine-readable evidence, not hand-copied metrics."""
import json
from eeg_apps_z15.run_soak_stage import OUT


def main():
    a=json.loads((OUT/'audit.json').read_text())
    m=json.loads((OUT/'manifest.json').read_text())
    c=json.loads((OUT/'candidate_manifest.json').read_text())
    d=json.loads((OUT/'deployment.json').read_text())
    s=a['soak'];r=s['report'];short=a['final_candidate_soak']
    lines=[
        '# Z15 持续回放、断流恢复及运行诊断', '',
        '2026-09-26。本轮无需佩戴，没有新采集人的标注脑电；既有实时服务与隔离回放分开。', '',
        '## 完成情况', '',
        f'- 30 分钟按实际节奏送入 {r["packets_expected"]:,} 包，实际消费 {r["packets_consumed"]:,} 包。发送历时 {s["producer"]["elapsed_seconds"]:.3f} 秒，测试主体历时 {r["wall_seconds"]:.3f} 秒。',
        f'- 基础持续运行验收：{"通过" if s["passed"] else "未通过"}；没有主流程异常、监测错误或遗留回放子进程。',
        f'- 父进程稳态 RSS 中位数从 {s["rss_early_median_kib"]/1024:.2f} MiB 到 {s["rss_final_median_kib"]/1024:.2f} MiB，变化 {s["rss_median_growth_kib"]/1024:.3f} MiB。不是永久无内存泄漏的证明。',
        f'- ARM 读取至处理的队列等待：观测 P95 {s["queue_sampled_p95_ms"]:.1f} ms，逐包累计峰值 {s["queue_run_max_ms"]:.1f} ms；最后一分钟观测中位数 {s["queue_final_minute_median_ms"]:.1f} ms。P95来自约每秒一次的快照，不是全部样本的 P95。',
        f'- 波形快照年龄：观测 P95 {s["snapshot_age_p95_s"]:.3f} s，最大 {s["snapshot_age_max_s"]:.3f} s；启动后过期观测 {s["stale_observations_after_startup"]} 次。显示跳过 {s["display_skipped"]} 帧，不是脑电丢包。',
        f'- 父进程 CPU 累计 {r["parent_cpu_seconds"]:.2f} s，已退出子进程累计 {r["children_cpu_seconds"]:.2f} s。子进程包括回放送包器、实际管道读取器、波形写入器；这不是纯推理耗时。',
        f'- 最终断流修复版本另完成 {short["report"]["requested_seconds"]} 秒实际节奏回归，消费 {short["report"]["packets_consumed"]:,} 包，无异常与遗留子进程；队列峰值 {short["queue_run_max_ms"]:.1f} ms。',
        '- 两份无新增故障输入的全部 55 个输出窗口与前版一致（状态/分类/计数精确一致，浮点 atol=1e-6、rtol=1e-7）。',
        '- 最终板端 21 项单元/接口检查通过；输入年龄保护版本另完成 60 秒按实际节奏回归。', '',
        '## 恢复行为', '',
        '检查时发现主情绪/疲劳分支没有与 SEED 候选同等明确的时间断流重置。本轮补齐：', '',
        '- 空闲超过 0.5 秒撤销主模型旧结果；启动和退出也主动写无效状态。',
        '- 超过 0.25 秒的读取时间间断、逆序时间或异常字节触发主模型清空滤波器、未完成窗口、SQI 和个人疲劳校准。恢复后重新积累连续数据。',
        '- SEED 候选仍使用原有短断流策略。其他模型没有可信基线保留证据，故不复用同一规则。', '',
    ]
    for case in a['recovery']['cases']:
        for check in case['checks']:
            delay=check['first_seed_prediction_after_s']
            lines.append(f'- {case["case"]}，中断 {check["gap_seconds"]:.0f} s：SEED 基线保留={check["seed_baseline_retained"]}；主模型首个新完整窗口在恢复后 {check["first_primary_window_after_s"]:.3f} s；SEED 首次预测延迟为 '+('无预测' if delay is None else f'{delay:.3f} s')+'。旧结果已撤销，主模型校准重新开始。')
    lines += ['', '合成正对照只测试状态机，不是脑电准确率证据。旧记录未满足可信基线条件时正确不保留。6 秒注入是在虚拟包时间中测试桥接恢复；真实持续无包时还受生产 5 秒串口超时及 systemd 重启规则控制，不把两者等同。', '',
        '## 网页和部署', '',
        f'- 额外并行第三条完整处理管线期间出现过载：30 分钟记录中有 {s["sampled_input_age_lower_bound_over_3s"]} 次约每秒观测的输入年龄下界超过 3 秒。不是零积压；负载退出后是否恢复见最后一分钟队列值。',
        '- 这暴露了文件刚刷新不等于脑电新鲜的问题。最终版以 ARM 输入包到快照的处理年龄加快照等待年龄判断 3 秒过期；API 会同时撤销主情绪/疲劳有效标记和 SEED 当前类别。',
        '- 主结果发布时也检查其输入年龄：超过 3 秒就写入无效结果，清除分数与情绪标签，避免队列恢复后重新显示刚写出的历史预测。',
        '- 新增板端快照年龄、读取队列当前/峰值等待、最近主窗口计算耗时、显示快照跳过数、主模型重置次数。',
        '- 快照与输入年龄均由板端计算，避免 PC 与板卡时钟不一致；超过 3 秒清空当前诊断和当前预测。这不包含射频传输时间。',
        '- 队列等待不含射频传输；主窗口计算不含独立 SEED 分支和浏览器绘图。',
        f'- 部署状态：`{d["phase"]}`。仅修改 `cyton_guardianloop.py`、`guardianloop_web.py`。模型、滤波系数、质量阈值、固定通道、PL bit/hwh 与网络配置没有改变。',
        f'- 备份：`{d["backup"]}`。',
        '- 服务重启属于本次部署操作，不能当作测试中自行崩溃。部署前后哈希及服务状态保存在 JSON 中。', '',
        '## 边界与复现', '',
        '- 30 分钟测试的是加入诊断的基础版本；断流修复版本另做 5 分钟实际节奏回归和完整故障回归；最终输入年龄保护版另做 60 秒实际节奏及接口拒绝过旧输入的测试。版本哈希分别保留，不能说最终同一版本已完整测试了 30 分钟。',
        '- 回放循环重复 81.128 秒记录，接缝为人工构造，不能证明真实佩戴连续 30 分钟的信号质量。',
        '- 两条 ARM 管线及部分低优先级回归同时存在；不是独占硬件性能，也不含无线链路、浏览器/网络的全端到端延迟。',
        '- 初版故障脚本重复解压序号数组，测试异常缓慢。仅终止了该隔离检查及其波形子进程，保留 `faults/` 中间文件；改成一次缓存后在 `faults_fixed/` 重跑，最终结果只采用重跑输出。没有借此调整算法。',
        f'- 基础目录：`{m["stage"]}`；最终版本检查：`{c["stage"]}`。',
        '- `PROTOCOL.md`：工程判据；`manifest.json` / `candidate_manifest.json`：版本和文件哈希；`audit.json`：结果与判定；`soak/monitor.jsonl`：逐次资源观测；`candidate/faults/recorded/events.json` 和 `candidate/faults/synthetic/events.json`：恢复证据；`deployment.json`：部署与备份。',
        '', '```powershell',
        '# 已有运行目录受保护。新的整轮复现应在 run_soak_stage.py 中指定新输出目录。',
        'D:\\Users\\lenovo\\anaconda3\\python.exe -m eeg_apps_z15.run_soak_stage',
        'D:\\Users\\lenovo\\anaconda3\\python.exe -m eeg_apps_z15.verify_soak_candidate',
        '# verify_stream_recovery.py 的最新脚本已修复读取开销；不要重跑本次专用的 PID 终止脚本。',
        '# 当前轮仅取回并审计结果（部署后旧生产哈希检查会失败，勿误当回归失败）：',
        'D:\\Users\\lenovo\\anaconda3\\python.exe -m eeg_apps_z15.collect_soak --final',
        '```', '',
        '下一步回到功能主线：整合已有八通道 SEED 候选展示与使用说明，保持其标签语义和正式 GAMEEMO/疲劳输出分离；无新的故障证据时不继续无限重复底层调试。',
    ]
    (OUT/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(OUT/'RESULTS.md')


if __name__=='__main__':main()
