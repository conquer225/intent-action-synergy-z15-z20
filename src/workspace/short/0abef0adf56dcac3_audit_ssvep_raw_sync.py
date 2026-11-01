"""Audit the six worn SSVEP diagnostic cues without changing the live system."""
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import platform

import numpy as np
import scipy
from scipy.signal import sosfilt, welch


BASE = Path(__file__).parent / 'output/ssvep_raw_sync_20261002'
OUT = BASE / 'six_trial_analysis'
CAP = ['F3', 'F4', 'C3', 'C4', 'T7', 'T8', 'O1', 'O2']
ELIGIBLE_REASONS = {
    'candidate_matches_cue', 'candidate_differs_from_cue',
    'three_consecutive_matching_windows',
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False) + '\n', encoding='utf-8')


def counts(values):
    return dict(sorted(Counter(str(value) for value in values).items()))


def load_capture(recording_id, sos):
    folder = BASE / 'recordings' / recording_id
    audit = read_json(folder / 'capture_audit.json')
    if not audit['raw_integrity_passed']:
        raise ValueError('Capture integrity was not verified')
    for name, expected in audit['sha256'].items():
        if sha256(folder / name) != expected:
            raise ValueError('Captured file changed: ' + name)
    meta = audit['metadata']
    if meta['channel_map'] != CAP or meta['sample_rate_hz'] != 250:
        raise ValueError('Fixed-cap/sample-rate mismatch')
    raw = np.fromfile(folder / 'samples_i32le.bin', dtype='<i4').reshape(-1, 8)
    arrival = np.fromfile(folder / 'arrival_mono_f64le.bin', dtype='<f8')
    indices = np.fromfile(folder / 'stream_index_u64le.bin', dtype='<u8')
    flags = np.fromfile(folder / 'flags_u8.bin', dtype='u1')
    if any(len(values) != meta['samples'] for values in (raw, arrival, indices, flags)):
        raise ValueError('Raw/alignment row counts disagree')
    selected = raw[:, 6:8].astype(np.float64) * meta['microvolts_per_count']
    rail = np.any(np.abs(raw[:, 6:8].astype(np.int64)) >= 8388607, axis=1)
    reset = ((flags & 3) != 0) | rail
    reset[0] = True
    reset[1:] |= (np.diff(arrival) > .25) | (np.diff(arrival) < 0)
    reset[1:] |= rail[:-1]
    boundaries = list(np.flatnonzero(reset)) + [len(raw)]
    filtered = np.empty_like(selected)
    for start, end in zip(boundaries, boundaries[1:]):
        filtered[start:end] = sosfilt(sos, selected[start:end] - selected[start], axis=0)
    rows = [json.loads(line) for line in
            (folder / 'linked_cue_events.jsonl').read_text(encoding='utf-8').splitlines()]
    return dict(folder=folder, audit=audit, meta=meta, raw=raw, selected=selected,
                filtered=filtered, arrival=arrival, indices=indices, flags=flags,
                rail=rail, reset=reset, events=rows)


def spectral_description(capture, onset, end):
    # USB receive time is an approximate marker, not the actual optical onset.
    a = int(np.searchsorted(capture['arrival'], onset + .5, side='left'))
    b = int(np.searchsorted(capture['arrival'], end - .25, side='right'))
    if b-a < 500 or capture['reset'][a:b].any():
        return dict(available=False, reason='short_or_discontinuous_post_marker_interval')
    spectra = {}
    for label in ('selected', 'filtered'):
        frequencies, power = welch(capture[label][a:b], fs=250, nperseg=500,
                                   noverlap=250, detrend='constant', axis=0)
        spectra[label] = power
    step = float(frequencies[1]-frequencies[0])
    result = dict(available=True, raw_row_start=a, raw_row_end_exclusive=b,
                  samples=b-a, nominal_seconds=(b-a)/250,
                  marker='USB receipt +0.5 s to trial_end -0.25 s; not optical',
                  welch_window_samples=500, welch_overlap_samples=250,
                  frequency_resolution_hz=step, power_units='microvolt_squared')
    for label, power in spectra.items():
        band = (frequencies >= 8) & (frequencies <= 14)
        per_channel = []
        for channel in range(2):
            def bp(center):
                mask = np.abs(frequencies-center) <= .5
                return float(power[mask, channel].sum()*step)
            ten = sum(bp(center) for center in (10, 20, 30))
            twelve = sum(bp(center) for center in (12, 24, 36))
            per_channel.append(dict(channel=CAP[6+channel],
                peak_8_14_hz=float(frequencies[band][np.argmax(power[band, channel])]),
                band_power_uv2={str(f): bp(f) for f in (10, 12, 20, 24, 30, 36, 50)},
                twelve_to_ten_harmonic_power_ratio=twelve/ten if ten else None))
        result[label] = per_channel
    return result


def audit_trial(capture, start):
    rows = [row for row in capture['events'] if row['trial_id'] == start['trial_id']]
    markers = [row for row in rows if row['event'] == 'presentation_receipt']
    ends = [row for row in rows if row['event'] == 'trial_end']
    if len(markers) != 1 or len(ends) != 1:
        raise ValueError('Missing or duplicate cue marker/end')
    onset, end = markers[0]['board_monotonic_s'], ends[0]['board_monotonic_s']
    if any(row['board_boot_id'] != capture['meta']['board_boot_id'] for row in rows):
        raise ValueError('Cue/raw boot identity mismatch')
    if not capture['arrival'][0] <= onset < end <= capture['arrival'][-1]:
        raise ValueError('Cue not covered by raw receive timestamps')
    shadows = [row for row in rows if row['event'] == 'shadow_snapshot']
    decisions = [row for row in rows if row['event'] == 'decision']
    eligible = [row for row in decisions if row['reason'] in ELIGIBLE_REASONS]
    accepted = [row for row in decisions if row['accepted']]
    snapshots = [row for row in shadows if row.get('state') == 'candidate_only'
                 and row.get('valid') is True and not row.get('stale')]
    warnings = Counter()
    for row in shadows:
        for channel in (row.get('quality') or {}).get('channels', []):
            for warning in channel.get('warnings', []):
                warnings[channel['channel'] + ':' + warning] += 1
    packet_rows = [int(np.searchsorted(capture['indices'], row['packets_seen']-1))
                   for row in snapshots if isinstance(row.get('packets_seen'), int)]
    if any(i >= len(capture['indices']) for i in packet_rows):
        raise ValueError('Candidate packet watermark outside raw capture')
    eligible_counts = counts(row['observed_hz'] for row in eligible)
    post_guard = [row for row in snapshots
                  if (row.get('source') == 'live'
                      and 0 <= row['input_age_seconds'] <= .5
                      and row['board_monotonic_s']-(row['shadow_updated_monotonic_s']-row['input_age_seconds']) <= .5
                      and row['shadow_updated_monotonic_s']-row['input_age_seconds'] >= onset+2.5
                      and not (row.get('quality') or {}).get('hard_bad'))]
    longest = Counter()
    last_index, last_frequency, streak = None, None, 0
    for row in shadows:
        if row not in post_guard:
            last_index, last_frequency, streak = None, None, 0
            continue
        index, frequency = row['window_end_index_exclusive'], row['frequency_hz']
        streak = streak+1 if (last_index is not None and index-last_index == 50
                              and frequency == last_frequency) else 1
        longest[str(frequency)] = max(longest[str(frequency)], streak)
        last_index, last_frequency = index, frequency
    return dict(trial_id=start['trial_id'], recording_id=start['raw_recording_id'],
        target_hz=start['target_hz'], board_start_marker_s=onset, board_end_marker_s=end,
        marker_duration_s=end-onset, raw_cue_coverage_passed=True,
        ever_matched=ends[0]['ever_matched'], end_reason=ends[0]['reason'],
        observed_windows=ends[0]['observed_windows'],
        missed_window_hops_lower_bound=ends[0]['missed_window_hops_lower_bound'],
        all_snapshot_states=counts(row.get('state') for row in shadows),
        unavailable_snapshot_reasons=counts(row.get('reason') for row in shadows
                                            if row.get('state') != 'candidate_only'),
        all_fresh_candidate_counts_hz=counts(row['frequency_hz'] for row in snapshots),
        eligible_decision_windows=len(eligible), eligible_candidate_counts_hz=eligible_counts,
        eligible_target_windows=eligible_counts.get(str(start['target_hz']), 0),
        accepted_matching_windows=len(accepted),
        first_match_after_receipt_s=accepted[0]['board_monotonic_s']-onset if accepted else None,
        maximum_streak=max((row['streak'] for row in decisions), default=0),
        decision_reasons=counts(row['reason'] for row in decisions),
        post_guard_fresh_candidate_counts_hz=counts(row['frequency_hz'] for row in post_guard),
        post_guard_candidate_longest_consecutive_runs_hz=dict(longest),
        idle_detection_validated=False,
        hard_bad_snapshot_count=sum(bool((row.get('quality') or {}).get('hard_bad')) for row in shadows),
        warning_snapshot_counts=dict(warnings),
        frame_ok_at_end=ends[0]['frame_ok'],
        spectral=spectral_description(capture, onset, end))


def main():
    segments = read_json(BASE / 'diagnostic_capture_segments.json')
    runtime = OUT / 'runtime'
    config = read_json(runtime / 'ssvep_causal_protocol.json')
    if config['fixed_cap'] != CAP or config['selected_cap_indices'] != [6, 7]:
        raise ValueError('SSVEP runtime channel contract differs')
    sos = np.load(runtime / 'ssvep_candidate_sos.npy', allow_pickle=False)
    captures = [load_capture(recording_id, sos) for recording_id in segments['capture_ids']]
    if len({c['meta']['board_boot_id'] for c in captures}) != 1:
        raise ValueError('Continuation crossed a reboot; inspect separately')
    if len({c['meta']['protocol_digest'] for c in captures}) != 1:
        raise ValueError('Continuation changed the protocol')
    trials = [audit_trial(capture, row) for capture in captures for row in capture['events']
              if row['event'] == 'trial_start']
    if [trial['target_hz'] for trial in trials] != [10, 0, 12, 0, 10, 12]:
        raise ValueError('Preserve and inspect any unexpected/extra cue attempts')
    summary = dict(created_pc_local=datetime.now().isoformat(),
        protocol_id=captures[0]['meta']['protocol']['protocol_id'],
        fixed_cap=CAP, classifier_channels=['O1', 'O2'],
        source='real worn Cyton; no optical sensor', control_enabled=False,
        raw_integrity_passed=True, raw_cue_coverage_passed=True,
        raw_samples=sum(c['meta']['samples'] for c in captures),
        raw_sequence_discontinuities=sum(c['audit']['sequence_discontinuities'] for c in captures),
        raw_malformed_rows=sum(int(np.count_nonzero(c['flags'] & 2)) for c in captures),
        raw_o1_o2_fullscale_rows=sum(int(c['rail'].sum()) for c in captures),
        capture_count=len(captures),
        capture_nominal_seconds=sum(c['meta']['samples']/250 for c in captures),
        capture_ids=segments['capture_ids'],
        total_logged_windows=sum(t['observed_windows'] for t in trials),
        missed_window_hops_lower_bound=sum(t['missed_window_hops_lower_bound'] for t in trials),
        flicker_trials_with_any_three_window_match=sum(t['ever_matched'] for t in trials if t['target_hz']),
        flicker_trial_count=sum(t['target_hz'] != 0 for t in trials),
        rest_is_protocol_no_control_not_validated_idle_detection=True,
        recognition_accuracy_not_claimed=True, optical_onset_verified=False,
        processing_parity_not_claimed=True,
        spectral_method='Descriptive Welch; existing causal SOS, reset at capture start/raw gap/fullscale; no fitting or tuning',
        hypotheses_tested=['Producer callbacks preserve consecutive observed windows',
                           '12 Hz cue can yield three matching windows in this wearer'],
        limitations=['One participant, only two cues per condition; overlapping windows are not independent trials',
                     'USB receipt and browser callbacks are not optical/ADC hardware synchronization',
                     'Rest output is disabled by cue; it is not learned non-target rejection',
                     'Any-match success does not prove stable recognition or controller safety',
                     'Fresh-candidate counts include pre-guard windows; eligible counts exclude engineering gate failures',
                     'Spectral filter is reconstructed at recording boundaries, not exact live filter-state replay'],
        runtime_sha256={p.name:sha256(p) for p in runtime.iterdir() if p.is_file()},
        input_audit_sha256={c['meta']['trial_id']:sha256(c['folder']/'capture_audit.json') for c in captures},
        script_sha256=sha256(Path(__file__)),
        software=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__),
        trials=trials)
    write_json(OUT / 'six_trial_audit.json', summary)
    lines = ['# 六次真实佩戴 SSVEP 定向排查', '',
        '固定帽位 F3,F4,C3,C4,T7,T8,O1,O2；候选仅使用 O1/O2。模型、滤波与质量门限未改，控制输出始终关闭。', '',
        f"两段录制共 {summary['raw_samples']} 行，名义 EEG 时长 {summary['capture_nominal_seconds']:.3f} 秒；原始文件及提示覆盖检查通过。",
        f"原始序号不连续 {summary['raw_sequence_discontinuities']}，畸形标记 {summary['raw_malformed_rows']}，O1/O2 满量程行 {summary['raw_o1_o2_fullscale_rows']}。",
        f"六次共观察 {summary['total_logged_windows']} 个窗口，日志中的漏窗下界 {summary['missed_window_hops_lower_bound']}。", '',
        '## 逐次日志结果', '']
    for number, trial in enumerate(trials, 1):
        target = f"{trial['target_hz']:g} Hz" if trial['target_hz'] else '休息/无目标'
        latency = (f"；首次匹配距软件呈现接收 {trial['first_match_after_receipt_s']:.3f} 秒"
                   if trial['first_match_after_receipt_s'] is not None else '')
        lines.append(f"- 第{number}次 {target}：观察 {trial['observed_windows']} 窗，曾三窗匹配 {trial['ever_matched']}{latency}；符合全部决策门控的 {trial['eligible_decision_windows']} 窗中，候选计数 {trial['eligible_candidate_counts_hz']}；接受匹配 {trial['accepted_matching_windows']} 窗。")
        lines.append(f"  全部新鲜候选（含保护期）{trial['all_fresh_candidate_counts_hz']}；决策原因 {trial['decision_reasons']}。")
    lines += ['', '## 解释边界', '',
        '四次闪烁中出现过匹配只能验证本轮互动链路；不能宣布 100% 识别准确率。结束时 accepted=false 是主动撤销旧结果，不表示整轮失败。',
        '休息分支由提示协议强制不控制，仍须分析原始候选的非目标误报，不能把这两次作为正确识别休息。',
        '短时 input_backlog/no_data 与漏包、漏窗不是同一指标；全部决策原因都保留，不能只挑 accepted 的窗口。',
        'display_timing_unreliable 大多位于帧统计尚未满2秒的初始化阶段；不能将该原因计数直接解释成屏幕异常次数。各试验结束时软件帧检查均通过，但无光学实测。',
        '原始与滤波后的 10/12 Hz 基频、二/三次谐波功率保存在 six_trial_audit.json；仅为软件/USB标记附近的描述性证据。',
        '光学频率与精确刺激起点未实测；本轮不能证明跨人性能、无目标检测或安全控制，未调参、未替换正式模型。', '',
        '## 原始证据与后续问题', '',
        '两次12 Hz的O1原始8–14 Hz谱峰均为12 Hz。频谱仅支持“本轮信号含有目标频率附近成分”，不能排除全部伪迹或证明总体准确率。',
        '两段原始序号均连续，但试验中仍有 input_backlog/no_data 事件。下一步可用这些已保存数据排查短时积压，不需再次佩戴。',
        'post_guard_candidate_longest_consecutive_runs_hz 保存了绕过提示分支时的原始候选连续长度；休息段仍可能连续指向某频率。上线无提示控制前必须独立评估非目标误触发，不能直接放行三窗候选。', '',
        '## 复现', '', '```powershell',
        "& 'D:\\ican\\codex_project\\eeg_apps_z15\\.venv-mi\\Scripts\\python.exe' -X utf8 'D:\\ican\\codex_project\\eeg_apps_z15\\audit_ssvep_raw_sync.py'",
        '```', '', '输入哈希、正式运行时代码/系数快照、逐窗日志、原始 ADC 与 USB 到达时间均保留；两段分开保存，不假装连续。']
    (OUT / 'RESULTS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in summary.items() if key not in
                      ('trials', 'runtime_sha256', 'limitations')}, ensure_ascii=False))
    brief_fields = ('target_hz', 'ever_matched', 'observed_windows',
                    'eligible_decision_windows', 'eligible_candidate_counts_hz',
                    'first_match_after_receipt_s', 'unavailable_snapshot_reasons',
                    'post_guard_candidate_longest_consecutive_runs_hz')
    for number, trial in enumerate(trials, 1):
        print(json.dumps(dict(number=number, **{key:trial[key] for key in brief_fields}),
                         ensure_ascii=False))


if __name__ == '__main__':
    main()
