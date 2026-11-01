"""Generate the result memo only from completed, audited predictions."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE/'output/mi_crossfield_stability_20261001'


def read(name):
    return json.loads((RUN/name).read_text(encoding='utf-8'))


def main():
    results, verify, counts = [read(name) for name in ('results.json', 'verification.json', 'integer_count_audit.json')]
    assert verify['passed'] and counts['passed']
    assert verify['results_sha256'] == counts['results_sha256']
    methods = results['methods']
    names = {'B0_ORIGINAL_EEGNET': '原EEGNet', 'EQUAL_BEST': '逐人等权／单点源最佳',
             'EQUAL_AVERAGE': '逐人等权／邻域平均＋源BN校准', 'RISK_BEST': '有界人风险／单点源最佳',
             'RISK_AVERAGE': '有界人风险／邻域平均＋源BN校准'}
    lines = ['# 固定八通道：原30人跨领域稳定性实验', '',
             '任务：左右手运动想象二分类。帽位始终为 `F3,F4,C3,C4,T7,T8,O1,O2`。', '',
             '这是反复使用的原开发30人LOSO探索实验，**不是新的独立确认、不是本人Cyton准确率，也不是控制安全验收**。独立12人及旧开发10人的EEG均未读取；没有上板、生成比特流或改正式服务。', '',
             '## 结果', '']
    for name, summary in methods.items():
        ci = summary['person_bootstrap_95_ci']
        lines += [f'- {names[name]}：平均BA **{summary["mean_person_ba"]*100:.4f}%**，逐人95%区间 {ci[0]*100:.4f}～{ci[1]*100:.4f}%；'
                  f'macro-F1 {summary["mean_person_macro_f1"]:.6f}；跨人SD {summary["between_person_sd"]*100:.4f}个百分点；'
                  f'最弱8人平均BA {summary["mean_lowest8_ba"]*100:.4f}%；低于55%的有{summary["people_below_55"]}人；'
                  f'每人内三种子的SD再按人平均为{summary["mean_seed_sd"]*100:.4f}个百分点。']
    lines += ['', '三种子42/43/44先在各人内平均，再按30人等权汇总。没有报最佳种子，也不是预测集成。各方法的“最弱8人”按该方法自己的逐人均值排序；不是只选择容易的人。', '',
              '## 预声明关口与结论', '',
              '主要候选仅为两种平均模型。相对原EEGNet须同时：平均BA提高至少1个百分点、两比较校正后的97.5%配对区间下限>0、最弱8人的均值提高至少1个百分点、跨人SD不增加。单点最佳仅为归因对照，不能失败后改称预声明候选。', '']
    for name in ('EQUAL_AVERAGE', 'RISK_AVERAGE'):
        comparison = results['paired_vs_original_eegnet'][name]
        ci = comparison['adjusted_97_5_paired_ci']
        lines += [f'- {names[name]}：平均增益{comparison["mean_ba_gain"]*100:+.4f}个百分点，校正配对区间'
                  f'{ci[0]*100:+.4f}～{ci[1]*100:+.4f}；最弱8人增益{comparison["mean_lowest8_gain"]*100:+.4f}；'
                  f'SD变化{comparison["between_person_sd_change"]*100:+.4f}；'
                  f'{comparison["people_improved"]}人提高／{comparison["people_declined"]}人下降／{comparison["people_tied"]}人相同；'
                  f'关口：{"通过" if comparison["stability_gate_passed"] else "未通过"}。']
    lines += ['', f'通过列表：{", ".join(results["passing"]) or "无"}。无论是否通过，本轮不授权部署；以前12人的确认数据已经暴露，不能回去再挑模型后称作独立确认。', '',
              '## 同场归因（描述性，不另挑赢家）', '']
    for a, b, description in [('EQUAL_BEST', 'B0_ORIGINAL_EEGNET', '只改变人风险的等权贡献'),
                              ('RISK_BEST', 'EQUAL_BEST', '等权基础上加入受限风险预算'),
                              ('EQUAL_AVERAGE', 'EQUAL_BEST', '等权轨迹上增加平均＋源BN重估'),
                              ('RISK_AVERAGE', 'RISK_BEST', '风险轨迹上增加平均＋源BN重估')]:
        delta = methods[a]['mean_person_ba']-methods[b]['mean_person_ba']
        low = methods[a]['mean_lowest8_ba']-methods[b]['mean_lowest8_ba']
        lines += [f'- {description}：平均BA变化 {delta*100:+.4f}个百分点；最弱8人均值变化 {low*100:+.4f}个百分点。']
    lines += ['', '这些消融能比较训练目标和“平均＋BN重估”这个组合，但不能把组合收益单独归因于平坦极小值，也没有独立分离平均与BN的贡献。没有测Hessian或因果机制。', '',
              '## 数据与可比性', '',
              f'- 相同26人拟合／3人源验证／1人外层目标，30折，3种子；原{results["all_trials"]}试次、{results["author_flagged_retained"]}作者异常标记全部保留。'
              f'各方法共同{results["scored_trials"]}评分试次，包括{results["scored_author_flags"]}异常标记；每人前60个试次与历史规则一致不计分，神经网络不做目标适配。',
              '- 滤波、8–30Hz输入、500样本窗口、源拟合人通道标准化、2226参数结构、Adam、batch64、200epoch上限与20epoch早停保持不变。旧已审计90次拟合作为原参考，新做180次拟合。不同训练目标可能触发不同早停，不是假定训练耗时完全相同。',
              f'- 新模型全部源冻结后才前向外层目标。实际总{results["source_epochs"]}epoch，训练与平均合计{results["pc_training_total_seconds"]:.3f}秒（PC GPU，不是ARM耗时）。', '',
              '## 从其他领域借什么', '',
              '- [GroupDRO作者仓库](https://github.com/kohpangwei/group_DRO)：图像／语言分类中按群体风险分配权重。本轮的变化是以源人作组、上一epoch损失EMA估风险、限制在等权0.5～2倍；保留早停与Dropout，不照搬原仓库依赖。不是原GroupDRO实验复现。',
              '- [SWAD作者仓库](https://github.com/khanrc/swad)、[NeurIPS2021原文页面](https://proceedings.neurips.cc/paper_files/paper/2021/hash/bcb41ccdc4363c6848a1d760f26c28a0-Abstract.html)：借用权重平均的图像域泛化思路。使用源验证最佳epoch的固定±2轮，平均后只用拟合人重估BN，不运行SWAD谷底搜索，不是原SWAD复现。',
              '- 此轮按用户要求不从EEG/MI论文筛选算法。上述机制本身已有来源；是否在EEG已有相同组合未核验，不声称“从未使用”“首次”或保证原创。', '',
              '## 公式与限制', '',
              '每epoch用全体拟合试次的在线CE更新每人风险EMA（新值系数0.2），前5轮等权。随后 `q_g=clip(c*exp((EMA_g-max(EMA))/0.5),0.5/G,2/G)`，选c使sum(q)=1；下一epoch样本权重为 `N*q_g/n_g`，minibatch使用mean(weight*CE)，不以batch权重总和二次归一化。',
              '代码用log尺度二分防止指数溢出，含−60数值下限。独立审计确认实际全部训练风险跨度未触及该下限，因此在本轮实际epoch上未改变声明公式；这不是对任意极端风险的精确KL投影保证。',
              '困难人的高CE可能来自真实域差异，也可能来自噪声／弱MI响应；本轮仅按已声明公式估计，未证明高CE一定代表值得加强学习的生理信号。',
              '平均浮点状态、整数BN计数取中心；然后源拟合人原顺序batch256校准BN，Dropout关闭、BN累计batch矩、无梯度，不用验证／目标波形。边界中心不足5轮时使用实际可用轮数并记录。部署推理仍是单网络；未测ARM时延。', '',
              '## 验证', '',
              '- 运行前44项测试通过，包括风险权重边界、均匀风险、排列不变、按人而非窗口等权、源BN校准无梯度／无Dropout随机数、源训练API不接收目标、重叠人员拒绝、重复种子一致。',
              f'- {verify["source_checkpoints_checked"]}源检查点重建中心与平均／BN状态，检查逐epoch权重延迟与范围、源验证选择。'
              f'CPU/GPU重新计算{verify["new_prediction_classes_recomputed"]}个新预测，类别完全一致；logits最大绝对误差 {verify["cpu_gpu_max_abs_logits_error"]:.12g}。',
              f'- 独立整数审计复算{counts["integer_predictions_checked"]}个预测（含原参考与预锁定BN诊断）、每个混淆矩阵、BA/F1、逐人聚合、自助法区间与全部关口。'
              f'风险数值最大跨度／温度为{counts["max_risk_scaled_span"]:.6f}，−60数值下限未使用。',
              '- 原代码／数据／模型哈希未变，正式恢复包未变；没有读取原始MAT、独立12人、旧开发10人或板卡。', '',
              '## 文件与复现', '',
              '- 冻结协议 `protocol.json`、模型配置 `network_config.json`、人员 `fold_manifest.json`、身份 `trial_manifest.json`、代码 `code_snapshot/`、输入哈希 `lock.json`。',
              '- 模型与历史 `source_checkpoints/`；全部源冻结 `source_training_complete.json`；新目标访问时刻 `target_access.json`；逐试次 `fold_predictions/`；结果 `results.json`；数值验证 `verification.json`；整数审计 `integer_count_audit.json`。',
              f'- 结果SHA256：`{verify["results_sha256"]}`。', '',
              '在 `D:\\ican\\codex_project\\eeg_apps_z15` 执行；现有结果禁止覆盖。若完整重新复现，使用新命名输出目录并记录为新运行，不能替换当前冻结证据。', '',
              '```powershell',
              '.\\.venv-mi\\Scripts\\python.exe -X utf8 -m unittest test_mi_crossfield_stability test_mi_model_comparison test_cho2017_pipeline test_cho2017_adaptation',
              '.\\.venv-mi\\Scripts\\python.exe -X utf8 mi_crossfield_stability.py prepare',
              '.\\.venv-mi\\Scripts\\python.exe -X utf8 mi_crossfield_stability.py train',
              '.\\.venv-mi\\Scripts\\python.exe -X utf8 mi_source_bn_diagnostic.py prepare',
              '.\\.venv-mi\\Scripts\\python.exe -X utf8 mi_audit_bn_buffers.py',
              '.\\.venv-mi\\Scripts\\python.exe -X utf8 mi_crossfield_stability.py evaluate',
              '.\\.venv-mi\\Scripts\\python.exe -X utf8 mi_source_bn_diagnostic.py evaluate',
              '.\\.venv-mi\\Scripts\\python.exe -X utf8 mi_crossfield_stability.py verify',
              '.\\.venv-mi\\Scripts\\python.exe -X utf8 audit_mi_crossfield_counts.py',
              '.\\.venv-mi\\Scripts\\python.exe -X utf8 report_mi_crossfield.py', '```', '',
              '以上为等价的串行复现依赖顺序；本次BN诊断prepare实际与主源拟合并行，二者都在新目标访问前冻结。`prepare`、已有`results.json`和整数审计拒绝覆盖；读取目标后`train`拒绝再拟合。', '',
              '## 后续边界', '',
              '若不通过，停止本轮这两个预声明候选，保留负结果，不换名字继续包装。若通过，也只提名作新独立数据验证；原12人不再用于挑选。正式情绪／疲劳／SSVEP不变，左右手仍是运动想象主线，五指分支不恢复。']
    diagnostic = read('source_bn_diagnostic/results.json')
    buffer_audit = read('source_bn_diagnostic/buffer_audit.json')
    ci = diagnostic['paired_95_ci_descriptive_not_primary_gate']
    lines += ['', '## 评分前另锁定的BN单独诊断对照', '',
              '在新目标分数尚未计算、主拟合仍运行时，源码核对提出额外归因控制。主协议／两个主要候选／关口未修改。该对照不增加拟合、不改原90个模型的学习权重、偏置或标准化，只用对应26名源拟合人重估BN，且90个派生模型在主目标访问前全部冻结。', '',
              f'原权重＋仅源BN校准：平均BA **{diagnostic["mean_person_ba"]*100:.4f}%**，'
              f'最弱8人均值{diagnostic["mean_lowest8_ba"]*100:.4f}%，跨人SD{diagnostic["between_person_sd"]*100:.4f}个百分点；'
              f'相对原参考{diagnostic["gain_vs_original"]*100:+.4f}个百分点，描述性95%配对区间{ci[0]*100:+.4f}～{ci[1]*100:+.4f}。', '',
              '仅用于定位BN运行统计这一步的影响，不能失败后换成主要赢家，也不能把未作多重校正的描述性区间拿来通过主门槛。它隔离原轨迹上的BN改动，但还没独立分离等权／风险新轨迹中“平均”与“BN校准”的所有交互。', '',
              f'独立再次核对90份派生模型全部学习张量逐位一致。逐模型按通道取方差比值torch中位数，再对90模型取numpy中位数；原／源校准后的比值为'
              f'第一层{buffer_audit["old_over_source_calibrated_variance_ratio_median"]["block1.0.running_var"]:.6f}、'
              f'第二层{buffer_audit["old_over_source_calibrated_variance_ratio_median"]["block1.2.running_var"]:.6f}、'
              f'第三层{buffer_audit["old_over_source_calibrated_variance_ratio_median"]["block2.3.running_var"]:.6f}。'
              '第三层前有Dropout，这是可测的源统计差异；不能仅凭该比值认定Dropout是所有识别错误的原因。逐模型证据见`buffer_audit.json`。', '',
              '相关文件：`source_bn_diagnostic/protocol.json`、`source_freeze.json`、`results.json`、逐试次`fold_predictions/`、冻结脚本副本。实际附加命令：', '',
              '```powershell',
              '.\\.venv-mi\\Scripts\\python.exe -X utf8 mi_source_bn_diagnostic.py prepare  # 主源拟合运行中，任何新目标访问前',
              '.\\.venv-mi\\Scripts\\python.exe -X utf8 mi_source_bn_diagnostic.py evaluate # 主源冻结与主评分完成后',
              '```']
    target = RUN/'RESULTS.md'
    if target.exists():
        raise RuntimeError('Existing report preserved')
    target.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(target)


if __name__ == '__main__':
    main()
