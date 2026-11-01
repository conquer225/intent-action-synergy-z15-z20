"""Generate the decision memo only after numerical and count audits pass."""
from pathlib import Path
import json
from hashlib import sha256

RUN = Path(__file__).resolve().parent / 'output/mi_bn_trainonly_20261002'


def read(name):
    return json.loads((RUN / name).read_text(encoding='utf-8'))


def main():
    target = RUN / 'RESULTS.md'
    if target.exists():
        raise RuntimeError('Existing report preserved')
    r, p, v, a = [read(name) for name in ('results.json', 'protocol.json', 'verification.json', 'integer_count_audit.json')]
    actual_hash = sha256((RUN / 'results.json').read_bytes()).hexdigest()
    assert v['passed'] and a['passed'] and v['results_sha256'] == a['results_sha256'] == actual_hash
    labels = {'CROSS_ORIGINAL': '原跨人模型', 'CROSS_SOURCE_BN': '原跨人＋仅源训练数据BN重估',
              'PERSON_ONLY': '本人80试次原模型', 'PERSON_BN': '本人80试次＋仅前80数据BN重估',
              'CROSS_MATCHED80': '跨人80样本预算原模型', 'MATCHED80_BN': '同一跨人80样本＋BN重估'}
    lines = ['# 固定八通道：仅训练数据BN重估对照', '',
        '2026-10-02；固定`F3,F4,C3,C4,T7,T8,O1,O2`，左右手运动想象。原30人反复开发的探索性机制检查；目标后段和既往源BN结果已暴露，不是新的盲独立确认。', '',
        '## 同分母结果', '']
    for method, m in r['methods'].items():
        lo, hi = m['person95ci']
        lines.append(f'- {labels[method]}（`{method}`）：BA **{100*m["mean_person_ba"]:.4f}%**；逐人95%区间{100*lo:.4f}～{100*hi:.4f}%；macro-F1 {m["mean_person_f1"]:.6f}；跨人SD{100*m["between_person_sd"]:.4f}个百分点；最弱8人均值{100*m["mean_lowest8_ba"]:.4f}%。')
    lines += ['', '先每人种子42/43/44平均，再对30人等权平均；不是最优种子或预测集成。六条件使用同一2480个唯一后段试次，每条件7440预测。含198个作者异常标记试次，不按质量删试次。每方法最弱8人单独排序。', '',
        '## 预声明比较与判定', '',
        '两项主要比较：源BN对原源模型（增益>=1个百分点），本人BN对本人原模型（>=3个百分点），同时要求校正97.5%配对bootstrap下限>0。这是继续研究／机制判断关口，不授权晋升或部署。其余两项95%区间仅描述性；多轮开发偏差没有因本轮校正而消失。', '']
    for name, c in r['comparisons'].items():
        lo, hi = c['paired_ci']
        verdict = ('主要关口通过' if c['development_gate'] else '主要关口未通过') if c['primary'] else '描述性对照，不改成主要候选'
        lines.append(f'- `{name}`：差{100*c["mean_gain"]:+.4f}个百分点，{100*c["coverage"]:g}%配对区间{100*lo:+.4f}～{100*hi:+.4f}；{c["people_improved"]}人提高／{c["people_declined"]}人下降；{verdict}。')
    source = r['comparisons']['CROSS_SOURCE_BN_minus_CROSS_ORIGINAL']
    personal = r['comparisons']['PERSON_BN_minus_PERSON_ONLY']
    lines += ['', '## 结论边界', '',
        ('仅源训练统计重估达到本轮继续研究关口，但尚无新独立受试者、Cyton或ARM证据，不能直接上线。' if source['development_gate'] else '仅源训练统计重估未达到跨人继续研究关口，不把小幅变化当作可靠跨人改善或部署依据。'),
        ('本人小样本重估达到预声明机制关口，支持归一化统计是这套小样本流程的一个可改善环节；不能证明它解释全部低分，更不是零标签跨人提升。' if personal['development_gate'] else '本人小样本重估未达到预声明机制关口；此前统计更新偏少的事实，不足以解释成有效准确率收益。'),
        '样本数、权重表示、时间变化、早停及模型偏差仍未完整因果分解；任何个人模型低分都不能证明固定帽位无效。没有挑弱者删除或更改本轮测试段。', '',
        '## 实现与输入边界', '',
        '- 所有可学习张量（包含BN仿射、dense与bias）逐位保持原样，标准化均值/尺度及检查点选择不变；没有梯度训练、参数搜索或个人LDA头再拟合。只替换270份副本的BN运行均值、运行方差和批次数。',
        '- 源重估只用对应26名源拟合人；排除3源验证人、外层目标人。个人重估只用本人原顺序0–79；80–119验证段和>=120测试段不参与统计。匹配预算只用上一轮冻结80拟合索引，不重新抽样。',
        '- 原始6080身份、515作者异常标记保留；新输入仍使用相同滤波和0.5–2.5秒500采样点窗口。个人前后段共享一次父实验，是明确诊断例外，不是跨日验证。',
        '- 沿用`mi_crossfield_stability.recalibrate_bn`：全部eval关闭Dropout、重置BN、BN临时train、momentum=None、一遍固定升序batch256，再恢复原momentum和全部eval。',
        '- 它是累计等批次权重的运行统计，最后短批也等权；后级BN接收前级的批归一化激活。不是逐层精确全训练总体矩；未用测试batch归一化，也未改变推理为train模式。',
        '- 既往源BN在更早起点曾从63.83变64.27%；本轮统一order>=120后段，且补充本人／匹配预算对照，不宣称从未做过该方法或首次创新。', '',
        '## 验证证据', '',
        f'- 全部{v["BN_states_cpu_rebuilt"]}份BN状态用CPU及同一训练输入重建；所有学习张量和输入尺度逐位一致。最大BN缓冲区绝对误差{v["max_abs_BN_buffer_error"]:.12g}，容差预声明rtol2e−5/atol2e−6。',
        f'- CPU复算{v["predictions_cpu_recomputed"]}预测，类别完全一致；最大分数绝对误差{v["max_abs_score_error"]:.12g}，预声明rtol2e−5/atol2e−5。',
        f'- 独立NumPy整数审计{a["integer_predictions_checked"]}预测、三组旧基线原数组、所有训练索引、混淆矩阵、BA/F1、逐人聚合、区间及关口通过；270状态先冻结才进行本轮新评分。',
        '- 单元测试包括拟合/验证/测试排除、同一80预算、固定帽位/人员/种子、禁止非BN张量变化、80样本单批的实际均值/方差、关闭Dropout、不产生梯度/随机状态变化。测试执行数另见RUN_STATUS.md。',
        '- 未打开旧开发10人、已暴露确认12人或原始MAT；不要求佩戴、不访问Z15、不导出ARM、不操作PL/正式服务/执行器。正式恢复包摘要保持不变。', '',
        '## 下一步原则', '',
        '不因个人条件高于本人原模型就自动换跨人模型；先检查它是否超过同段原跨人参考，以及是否需要本人标签/适配。仍限原开发30人探索。若源重估无可靠收益，不继续重复微调BN；应转向保留源知识的适配／不同表示，在新协议里控制预算。已暴露12人不得用于反复选模后称独立确认。', '',
        '## 复现与文件', '',
        f'结果SHA256：`{actual_hash}`。',
        '`protocol.json`、`case_manifest.json`、`lock.json`、`code_snapshot/`、`models/`、`source_freeze.json`、`target_access.json`、`fold_predictions/`、`results.json`、`verification.json`、`integer_count_audit.json`。',
        '命令在`D:/ican/codex_project/eeg_apps_z15`运行。已有输出不可覆盖；独立重跑使用隔离副本和新的输出目录，审计及报告的RUN同步指向新目录。', '', '```powershell',
        r'.\.venv-mi\Scripts\python.exe -X utf8 -m unittest test_mi_bn_trainonly test_mi_crossfield_stability test_mi_person_transfer test_mi_model_comparison test_cho2017_pipeline test_cho2017_adaptation',
        r'.\.venv-mi\Scripts\python.exe -X utf8 mi_bn_trainonly.py prepare',
        r'.\.venv-mi\Scripts\python.exe -X utf8 mi_bn_trainonly.py calibrate',
        r'.\.venv-mi\Scripts\python.exe -X utf8 mi_bn_trainonly.py evaluate',
        r'.\.venv-mi\Scripts\python.exe -X utf8 mi_bn_trainonly.py verify',
        r'.\.venv-mi\Scripts\python.exe -X utf8 audit_mi_bn_trainonly.py',
        r'.\.venv-mi\Scripts\python.exe -X utf8 report_mi_bn_trainonly.py', '```', '']
    target.write_text('\n'.join(lines), encoding='utf-8')
    print(target)


if __name__ == '__main__':
    main()
