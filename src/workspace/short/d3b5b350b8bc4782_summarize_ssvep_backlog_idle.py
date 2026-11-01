"""Join saved-session diagnosis and the protected, isolated ARM timing evidence."""
from collections import Counter
from datetime import datetime
import json
from pathlib import Path

import numpy as np

from audit_ssvep_backlog_idle import OUT, BASE
from audit_ssvep_raw_sync import read_json, sha256, write_json


def main():
    session=read_json(OUT/'saved_session_diagnostics.json')
    case=OUT/'arm_replay_profile'
    run=case/'run'
    preservation=read_json(case/'preservation.json')
    if not all(preservation.values()):
        raise ValueError('Formal runtime/service restoration has not passed')
    report=read_json(run/'report.json')
    if (report['error'] or report['monitor_errors'] or report['remaining_children']
            or report['packets_consumed'] != 39000 or report['filter_backend'] != 'arm'):
        raise ValueError('Replay did not complete cleanly')
    raw=run/'recordings/0000000000000001'
    original=BASE/'recordings/d106522f443ce69b'
    for name, dtype, width in [('samples_i32le.bin','<i4',8),('sequence_u8.bin','u1',1),
                              ('flags_u8.bin','u1',1),('stream_index_u64le.bin','<u8',1),
                              ('arrival_mono_f64le.bin','<f8',1)]:
        data=np.fromfile(raw/name,dtype=dtype)
        if data.size != 39000*width:
            raise ValueError('Private raw recording row count mismatch: '+name)
        if name in ('samples_i32le.bin','sequence_u8.bin','flags_u8.bin'):
            source=np.fromfile(original/name,dtype=dtype)[:39000*width]
            if not np.array_equal(data,source):
                raise ValueError('Private replay raw mismatch: '+name)
    stages=read_json(run/'stages.json')
    slow=read_json(run/'slow_packets.json')
    results=read_json(run/'primary_results.json')
    monitor=[json.loads(s) for s in (run/'monitor.jsonl').read_text().splitlines()]
    slow_primary=[r for r in slow if (r['packet']+1)%500==0]
    final=results[-1]['result']
    if final['valid'] or final.get('emotion',{}).get('valid'):
        raise ValueError('Replay end did not withdraw previous primary results')
    best=sorted(slow,key=lambda r:-r['wall_ms'])[:8]
    top=[]
    for packet in best:
        top.append(dict(**packet, substeps=[r for r in stages['slow']
                                           if r['packet']==packet['packet']]))
    summary=dict(created_pc_local=datetime.now().isoformat(), source='offline_replay_not_live',
        real=False, new_human_data=False, input_repeated=False, original_samples_replayed=39000,
        independent_accuracy_claimed=False, controls_enabled=False,
        formal_preservation=preservation, replay_report=report,
        replay_raw_adc_sequence_flags_exact=True,
        calibrated_emotion_prediction_results=sum(r['result'].get('emotion',{}).get('state')=='prediction'
                                                 for r in results),
        fatigue_inference_windows=stages['stages']['fatigue_window']['calls'],
        primary_states=dict(Counter(r['result']['state'] for r in results)),
        seed_observed_states=dict(Counter(r.get('seed',{}).get('state') for r in monitor)),
        slow_packets_over_50ms=len(slow), slow_packets_at_500_sample_boundary=len(slow_primary),
        top_slow_packets=top, stages=stages['stages'],
        final_previous_prediction_withdrawn=True,
        diagnostic_evidence_hashes={str(p.relative_to(OUT)):sha256(p) for p in
            [OUT/'saved_session_diagnostics.json',case/'PLAN.json',case/'before.json',
             case/'after.json',case/'preservation.json',run/'stages.json',run/'report.json',
             run/'slow_packets.json',run/'primary_results.json']},
        limitations=['Instrumentation changes timing; one replay is not a performance improvement A/B test',
                     'USB radio/browser rendering/active display heartbeat are not reproduced',
                     'Packet cadence is regenerated at 250 Hz; original receive-time jitter is not reproduced',
                     'Formal web service remains active; not all OS scheduling/I/O delays are attributed',
                     'Private recorder start-counter metadata has a one-packet offset; raw rows independently checked',
                     'Generic harness prose says repeated; this input is 39000 rows for 39000 emitted packets, without wrap',
                     'Nested original source fields in the raw harness result are retained; the entire case is offline only'])
    write_json(OUT/'ARM_DIAGNOSTICS.json',summary)
    lines=['# SSVEP 积压与休息候选：离线排查结果','',
        '已完成六次真实记录审计及 156 秒隔离 ARM 回放；无需重新佩戴。',
        '正式采集服务已恢复。正式代码/模型/系数/.bit/.hwh 与服务配置哈希均未改变；未重启、未加载 PL。','',
        '## 已验证','',
        '- 两段原始数据输入哈希通过。六次提示共216个窗口，17个 input_backlog 全部保留。',
        '- 17次中9次距最近主任务窗口仅10个样本，4次距60个样本。'
        '在主任务后前50样本的21个候选中有9次积压，其余195个中有8次。'
        '这说明积压集中在主任务附近，但不能把窗口当独立统计样本。',
        '- 提示窗口附近最大 USB 接收间隔约91.16 ms；没有原始序号缺口、畸形标记或O1/O2满量程。',
        '- 本轮保护期后合格窗口重算CCA与存档分数最大差1.96e-12。'
        '重建从录制边界初始化，不代表已获得全部实时滤波状态。',
        f"- 板端定速回放处理 {report['packets_consumed']} / 39000 包，"
        f"输入年龄p95 {report['packet_input_age_p95_ms']:.1f} ms，最大 {report['packet_input_age_max_ms']:.1f} ms。",
        f"- 单包处理最高 {report['packet_compute_max_ms']:.1f} ms；"
        f"≥50ms慢包共{len(slow)}个，其中{len(slow_primary)}个位于500样本边界。",
        '- 回放ADC、序号、标记与源记录前39000行逐项完全一致；未循环重复数据。',
        f"- 情绪实际预测{summary['calibrated_emotion_prediction_results']}次；"
        f"疲劳结果状态计数{summary['primary_states']}；SEED观察到预测状态，SSVEP候选持续运行。",
        '- 结束时主任务及情绪旧结果已撤销；监视器无异常，子进程均退出。','',
        '## 慢点与判断','',
        '阶段是嵌套测量，不能直接把父子阶段相加。最大慢包的同包子阶段保存在 ARM_DIAGNOSTICS.json。']
    lines.append('primary_sqi/primary_filter 是共享类方法的计时标签，也包含 SEED 内部复用的同类调用；'
                 '不能把它们全部归为主情绪/疲劳分支。')
    for name in ['seed_packet','emotion_feature','primary_sqi','recorder_flush','primary_filter',
                 'ssvep_quality','ssvep_cca_scores','emotion_svm']:
        stage=stages['stages'][name]
        lines.append(f"- {name}：{stage['calls']}次，最高{stage['max_wall_s']*1000:.1f}ms，"
                     f"总墙钟{stage['wall_s']:.3f}s / 线程CPU{stage['cpu_s']:.3f}s。")
    lines += ['',
        '已验证的工程问题是同步计算形成短时峰值：500样本SEED处理、主任务质量计算、'
        '12秒协方差特征读取，以及偶发录制/状态写盘等待在同包叠加。'
        '这比“把小CCA矩阵搬到PL”更值得先处理。滤波/矩阵速度并不是这轮最主要的单次慢点。',
        '墙钟减线程CPU包含调度、磁盘与锁等待，不能把差值全部叫磁盘耗时。'
        '未做改善A/B，因此本轮只完成定位，未宣称消除积压。','',
        '## 休息分支：探索保留与否决','',
        '现有closed-set CCA必选8/10/12/14第一名，没有学习或校准“无目标”。'
        '以下只比较保护期后原始新鲜候选，未模拟全部显示门控；休息提示始终禁止控制。']
    for name in ['closed_set','score_030_margin_005','score_040_margin_010','off_grid_competitor']:
        flicker=[t['exploratory_rules'][name] for t in session['trials'] if t['target_hz']]
        rests=[t['exploratory_rules'][name] for t in session['trials'] if not t['target_hz']]
        lines.append(f"- {name}：四次闪烁保留窗口数{[r['retained_windows'] for r in flicker]}；"
                     f"两次休息保留数{[r['retained_windows'] for r in rests]}；"
                     f"休息出现三连同频候选{[r['any_three_same_frequency_run'] for r in rests]}。")
    lines += ['',
        '较宽score/margin规则仍在第二段休息出现三连假候选；竞争频率规则仍在第一段休息出现四连假候选，'
        '两者均不足以开放无提示控制。较严0.40/0.10规则在这两段休息拒绝全部候选，但首次10Hz'
        '只保留4/23窗口；一人六次数据不能独立验证该门限，未选择上线。',
        '结论：继续保留提示式交互和休息禁止控制，不把候选第一名当成安全命令。',
        '研究技能要求保留失败窗口且隔离探索与验证；本轮据此未替换正式门限或模型。','',
        '## 失败记录与限制','',
        '- arm_replay：首次sudo免密检查失败，未停止服务；保留其PLAN及前后保护检查。',
        '- arm_replay_authorized：停止后检查使用的旧命令包装器把inactive返回码视为异常，'
        '尚未运行回放即恢复原服务；保护检查全部通过。',
        '- arm_replay_profile：修正隔离脚本检查后完成一次156秒ARM回放；未改正式程序。',
        '- 回放没有真实USB/屏幕光学时序，没有活动刺激或提示心跳；网页网络渲染未计入。',
        '- 私有录制的起始计数元数据存在1包偏移；原始ADC/序号/标记/行数另行精确核对，'
        '不能把该私有录制直接混作新的人体数据。',
        '- 通用回放日志仍使用旧“repeated”措辞，内部原始结果保留cyton_usb字段；'
        '本案例由目录/PLAN/ARM_DIAGNOSTICS明确标记offline_replay_not_live，输入未重复。','',
        '## 下一步','',
        '只在隔离候选中优化同步计算峰值：先将主任务/SEED的重计算与采集消费解耦，'
        '使用有界任务队列、时间戳和代次检查，断流立即撤销，不能排队输出旧预测；'
        '其次减少协方差特征的逐行Python对象转换和重复SQI计算。'
        '用相同156秒记录做数值一致性与耗时A/B，失败保留，不急于上线或迁移PL。','',
        '## 复现','', '```powershell',
        "& 'D:\\ican\\codex_project\\eeg_apps_z15\\.venv-mi\\Scripts\\python.exe' -X utf8 'D:\\ican\\codex_project\\eeg_apps_z15\\audit_ssvep_backlog_idle.py'",
        "& 'D:\\ican\\codex_project\\eeg_apps_z15\\.venv-mi\\Scripts\\python.exe' -X utf8 'D:\\ican\\codex_project\\eeg_apps_z15\\summarize_ssvep_backlog_idle.py'",'```',
        '重新运行板端回放须重新确认临时停止授权并指定全新输出目录；不能覆盖上述三个案例。']
    (OUT/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(preservation=preservation, raw_exact=True,
        slow_packets=len(slow), slow_at_primary_boundary=len(slow_primary),
        primary_states=summary['primary_states'], seed_states=summary['seed_observed_states']),ensure_ascii=False))


if __name__=='__main__':
    main()
