"""Write the decision memo after CPU and independent integer audits pass."""
from pathlib import Path
import json

HERE=Path(__file__).resolve().parent
RUN=HERE/'output/mi_person_transfer_diagnostic_20261002'


def read(name):
    return json.loads((RUN/name).read_text(encoding='utf-8'))


def main():
    target=RUN/'RESULTS.md'
    if target.exists():
        raise RuntimeError('Existing report preserved')
    r,p,v,a,t=[read(name) for name in ('results.json','protocol.json','verification.json','integer_count_audit.json','training_metadata_audit.json')]
    assert v['passed'] and a['passed'] and t['passed']
    assert v['results_sha256']==a['results_sha256']==t['results_sha256']
    names={'CROSS_ORIGINAL':'原跨人模型（本轮共同后段）','PERSON_ONLY':'仅本人前80试次训练',
           'SOURCE_PERSON_HEAD':'冻结源特征＋本人80标签分类头','CROSS_MATCHED80':'跨人80样本／40验证预算对照'}
    lines=['# 固定八通道：个人可分性与跨人迁移诊断','',
           '2026-10-02；左右手运动想象，固定 `F3,F4,C3,C4,T7,T8,O1,O2`。原开发30人重复使用的探索结果，不是独立确认、零标签跨人改善、Cyton准确率或部署验收。','',
           '## 先纠正数据身份','',
           '原本拟比较“同人跨记录”；审计发现缓存是同次实验的独立7秒试次，并无明确跨日或逐试次run标签，故本轮只做**同次实验按原顺序分块，前段训练、后段测试**。',
           '数据论文的Experimental design / Experiment and datasets、Figure2与Table1描述每轮左右各20试次、5或6轮。缓存每连续40试次确实20/20，序列键严格递增；这些事实支持40试次块与实验轮次相符的推断，但不是核实run身份或真实连续时间。',
           '数据设计来源：[Cho2017原论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC5493744/)；本地 `D:/ican/datasets/Cho2017/source_docs/author_fulltext.xml`、`readme_100295.txt`。本轮仅核验采集结构，没有用该论文的分类方法找算法。','',
           '## 同分母结果','']
    for method,m in r['methods'].items():
        ci=m['person95ci']
        lines.append(f'- {names[method]}：平均BA **{100*m["mean_person_ba"]:.4f}%**，逐人95%区间{100*ci[0]:.4f}～{100*ci[1]:.4f}%；macro-F1 {m["mean_person_f1"]:.6f}；跨人SD{100*m["between_person_sd"]:.4f}个百分点；最弱8人均值{100*m["mean_lowest8_ba"]:.4f}%。')
    lines+=['','每人种子42/43/44先平均，再对30人等权平均；无最佳种子挑选或预测集成。每方法的最弱8人由该方法自己的逐人均值排序。',
            f'本轮各条件共有{r["scored_unique_trials"]}个唯一后段测试试次，包含{r["scored_author_flags"]}作者异常标记，未因质量删试次。每方法三种子7440预测。原参考只重新聚合相同后段，而不是直接借用上一轮order>=60的63.83%。','',
            '## 预声明诊断关口','',
            '两项主要诊断比较分别为PERSON_ONLY、SOURCE_PERSON_HEAD对CROSS_ORIGINAL。平均增益>=5个百分点且两比较校正后的97.5%配对bootstrap区间下限>0，才支持“此80标签预算下存在可观个人适配空间”；即使通过也不授权模型晋升或部署。','']
    for key,c in r['comparisons'].items():
        ci=c['paired_ci']
        lines.append(f'- `{key}`：增益{100*c["mean_gain"]:+.4f}个百分点，{100*c["coverage"]:g}%配对区间{100*ci[0]:+.4f}～{100*ci[1]:+.4f}；{c["people_improved"]}人提高/{c["people_declined"]}人下降；'+
                     (f'诊断关口{"通过" if c["diagnostic_headroom_gate"] else "未通过"}。' if c['primary'] else '描述性消融，不是新增主要候选。'))
    passing=[key for key,c in r['comparisons'].items() if c['diagnostic_headroom_gate']]
    lines+=['','通过的诊断比较：'+(', '.join(passing) if passing else '无')+'。',
            '若个人方法更高，合理解释仅为同次实验中本人有标签信息可被利用；不能说明新表示已经提升零校准跨人准确率。若个人方法低，也不能断言帽位无效或信号不可分：80训练标签与240维读出/2226参数网络可能不足。匹配预算对照约束样本数，但本人/跨人训练身份、标签和验证时序仍不同，不是完整因果分解。','',
            '## 本轮具体结论','',
            '在共同后段，保留源特征的本人分类头比本人从头训练高8.1435个百分点（描述性95%配对区间+4.4167～+12.4907），但仍比原跨人模型低2.6759个百分点（主要比较校正97.5%区间−5.2177～−0.1018）。这是保留源表示的价值，不是当前最高模型准确率的提升。',
            '本人80标签训练对跨人80样本预算对照只高1.3565个百分点，95%配对区间−0.6297～+4.1345跨零；不能据此声称“只要同人训练就会明显更好”。全源数据模型强于两个80样本神经模型，但尚未把样本数、受试者差异、早停和归一化影响逐一因果分离。',
            '因此不晋升任何个人方案，也不把52.56%解释成八通道或当前帽位无效。与上一轮仅微调权重相比，这轮给出了下一步更具体的诊断对象：小样本训练的归一化运行统计和保留源知识的适配方式。','',
            '## 评分后训练机制检查（描述性，不另造候选）','',
            '只读取已冻结的270份神经训练元数据（旧90＋新180），不重新拟合或前向EEG。按实际batch64与BN动量0.01，用 `(1−momentum)^更新次数` 计算初始统计项的理论残留系数；这个系数不是实测归一化误差，也不直接预测准确率。','']
    for method,m in t['models'].items():
        lines.append(f'- {names[method]}：选定epoch中位数{m["median_best_epoch"]:g}、对应训练批次更新中位数{m["median_updates_at_selected_checkpoint"]:g}、初始BN项理论残留系数中位数{m["median_theoretical_initial_BN_coefficient"]:.9g}；90个检查点中{m["selected_validation_at_or_below_chance"]}个最佳验证BA仍不超过0.5。')
    lines+=['','小样本检查点的初始BN项系数接近0.9，原跨人检查点约1e−8，提示“沿用同一epoch早停配方”并不等于相同的归一化充分度。此线索是评分后发现的假设，不是已证实低分原因；不能据此直接调整阈值、重选早停检查点或重写本轮结果。','',
            '## 准确做了哪些训练','',
            '- PERSON_ONLY：本人order0–79共80试次训练，80–119共40试次用于最早最佳BA早停，>=120全部测试。通道标准化只拟合前80；原EEGNet/Adam/batch64/最大200epoch/20epoch耐心保持不变。',
            '- CROSS_MATCHED80：原折26源拟合人、3源验证人不变；按人/类别近等权抽80训练（40/类）、40验证（20/类）；同样网络与学习配置。抽样不是去除异常标记；未被抽中的原始身份仍保留。',
            '- SOURCE_PERSON_HEAD：旧原模型和源通道标准化冻结，CPU提取dense前240维。StandardScaler和LDA（lsqr，auto收缩）只用本人前80标签拟合，不用40验证试次调头参数；替换原dense读出器，因此和原网络的推理头不同。没有微调特征层、BN、滤波或帽位。',
            '- CROSS_ORIGINAL：直接使用旧已审计90份模型/预测，只抽取共同测试后段；CPU审计还重算该后段原模型结果。',
            '- 所有270个新模型/头先冻结再统一前向后段。原代码和旧参考模型未改，未读取12人或旧10人的EEG。原始MAT没有打开，正式服务、ARM、PL、执行器不操作。','',
            '## 已验证与未验证','',
            '- 44项单元测试通过：原顺序划分/边界、人员和类别抽样配额、重复抽样确定、目标排除、缺类/重复索引拒绝、240试次人数、冻结特征不改变权重/BN/随机状态，特征不依赖dense分类器。',
            f'- CPU复算{v["predictions_cpu_recomputed"]}预测，类别完全一致；最大绝对分数误差{v["max_abs_score_error"]:.12g}。180份神经模型的拟合标准化和源选择核对，90个本人分类头从早期特征/标签重新重建。',
            f'- 独立NumPy整数审计{a["integer_predictions_checked"]}预测、全部混淆矩阵、BA/F1、逐人聚合、bootstrap区间及关口，核实样本配额和冻结先于新评分。',
            '- 6080试次、515个作者异常标记全部身份保留，缓存无逐位相同的重复波形。没有删除低分受试者；同人分块是明确声明的同一父记录划分诊断例外，不能作为主要跨人验证。',
            '- 尚未验证：跨日稳定性、真实Cyton连续处理与参考方式迁移、零标签新受试者收益、ARM耗时、静息误触发和安全闭环。','',
            '## 下一步边界','',
            '下一轮先另立开发协议，比较“训练集独立重估BN运行统计”与“不重估”，固定已有权重和划分，优先核对这种通用训练机制，而不是立即引入复杂网络。原跨人模型只可用对应26名源训练人；个人诊断只可用本人前80训练试次，不能用后40验证或后段测试EEG来计算统计。个人归一化结果仍属于有标签个人诊断，不能冒充零校准跨人提升。',
            '若重估仍无收益，再考虑保留源读出的受约束适配或不同表示；不把替换个人分类头已经低于源模型的方案直接上线。未开始下一轮拟合，尚无BN重估效果或新准确率。',
            '所有未来改善仍限固定八通道和左右手，不恢复五指；这30人反复用于开发，仅能做探索性评价。已暴露12人不能反复用于选模后称独立确认。板端、ARM/PL、正式恢复包全部不改。','',
            '## 证据与复现','',
            f'主结果SHA256：`{v["results_sha256"]}`。',
            '`protocol.json`、`case_manifest.json`、`input_audit.json`、`lock.json`、`code_snapshot/`、`models/`、`source_freeze.json`、`target_access.json`、`fold_predictions/`、`results.json`、`verification.json`、`integer_count_audit.json`、`training_metadata_audit.json`。',
            '在 `D:/ican/codex_project/eeg_apps_z15` 执行。以下记录原运行顺序，已有prepare、冻结模型、结果、审计和报告禁止覆盖；独立复现应使用隔离工程副本/新输出目录，审计与报告的RUN也须指向新目录。','',
            '```powershell',
            r'.\.venv-mi\Scripts\python.exe -X utf8 -m unittest test_mi_person_transfer test_mi_model_comparison test_cho2017_pipeline test_cho2017_adaptation',
            r'.\.venv-mi\Scripts\python.exe -X utf8 mi_person_transfer_diagnostic.py prepare',
            r'.\.venv-mi\Scripts\python.exe -X utf8 mi_person_transfer_diagnostic.py train',
            r'.\.venv-mi\Scripts\python.exe -X utf8 mi_person_transfer_diagnostic.py evaluate',
            r'.\.venv-mi\Scripts\python.exe -X utf8 mi_person_transfer_diagnostic.py verify',
            r'.\.venv-mi\Scripts\python.exe -X utf8 audit_mi_person_transfer_counts.py',
            r'.\.venv-mi\Scripts\python.exe -X utf8 audit_mi_person_transfer_training.py',
            r'.\.venv-mi\Scripts\python.exe -X utf8 report_mi_person_transfer.py','```','']
    target.write_text('\n'.join(lines),encoding='utf-8')
    print(target)


if __name__=='__main__':
    main()
