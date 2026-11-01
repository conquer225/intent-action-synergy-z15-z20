"""Decision report only after independent coefficient/numerical/count checks."""
from pathlib import Path
import json
from hashlib import sha256

RUN = Path(__file__).resolve().parent/'output/mi_source_residual_20261002'


def read(name):
    return json.loads((RUN/name).read_text(encoding='utf-8'))


def main():
    target = RUN/'RESULTS.md'
    if target.exists():
        raise RuntimeError('Completed report preserved')
    p,r,v,a = [read(name) for name in ('protocol.json','results.json','verification.json','integer_count_audit.json')]
    result_hash = sha256((RUN/'results.json').read_bytes()).hexdigest()
    assert v['passed'] and a['passed'] and v['results_sha256']==a['results_sha256']==result_hash
    labels = {'CROSS_ORIGINAL':'原跨人源模型','SOURCE_PERSON_HEAD':'既有80标签个人LDA分类头',
              'SOURCE_BOUNDED_RESIDUAL':'源读出＋有界个人残差','SOURCE_FREE_RESIDUAL':'源读出＋无内层限幅残差'}
    lines = ['# 固定八通道：源读出＋有界个人残差', '',
        '2026-10-02；左右手运动想象，`F3,F4,C3,C4,T7,T8,O1,O2`。原30人重复开发的有标签少样本适配，不是零标签跨人、盲独立确认、跨日或真实Cyton准确率。', '',
        '## 同一后段结果','']
    for method,m in r['methods'].items():
        lo,hi=m['person95ci']
        lines.append(f'- {labels[method]}（`{method}`）：BA **{100*m["mean_person_ba"]:.4f}%**，逐人95%区间{100*lo:.4f}～{100*hi:.4f}%；macro-F1 {m["mean_person_f1"]:.6f}；跨人SD{100*m["between_person_sd"]:.4f}个百分点；最弱8人平均{100*m["mean_lowest8_ba"]:.4f}%。')
    lines += ['', '先每人平均三种子42/43/44，再对30人等权平均；不是最优种子或集成。四条件共用2480个唯一后段试次，每方法7440预测，保留198个作者异常标记试次。旧63.83%的测试起点更早，不直接混用。', '',
        '## 预声明比较和判定','',
        '主要比较仅有界残差减原源：平均增益≥2个百分点，95%人员配对bootstrap下限>0，每方法各自最弱8人平均分下降≤1个百分点；三项同时满足才通过开发关口，仍不自动授权部署。其余比较仅描述性，不事后追加主要候选。10,000次人员bootstrap；本轮一项主要比较，无多比较校正，但多轮开发偏差依然存在。','']
    for key,c in r['comparisons'].items():
        lo,hi=c['paired_ci']
        verdict=('主要关口通过' if c['development_gate'] else '主要关口未通过') if c['primary'] else '描述性，不追加赢家'
        lines.append(f'- `{key}`：差{100*c["mean_gain"]:+.4f}个百分点，95%配对区间{100*lo:+.4f}～{100*hi:+.4f}；最弱8人差{100*c["lowest8_mean_difference"]:+.4f}个百分点；{c["people_improved"]}人提高／{c["people_declined"]}人下降；{verdict}。')
    primary=r['comparisons']['SOURCE_BOUNDED_RESIDUAL_minus_CROSS_ORIGINAL']
    lines += ['', '## 是否继续这套方法','',
        ('有界残差达到本轮开发关口，支持继续离线研究，但并非新独立证据，不导出ARM／上线。' if primary['development_gate'] else '有界残差未达到预声明关口，本配方不晋升。不会用更换上限、网格、种子或测试起点来把负结果改成通过。'),
        '有界保护的是源模型分数，不保证源判断本身正确；softmax分数不是经外部校准的置信度。限幅会同时阻止一些误改与一些有用纠正。不能泛化为所有适配无效，也不能证明固定帽位无效。','',
        '## 输出变更与恒等回退','']
    for method,d in r['diagnostics'].items():
        lines.append(f'- `{method}`：90个case中{d["identity_fallback_cases"]}个选恒等；7440预测中修改{d["changed_predictions"]}、纠正{d["rescued_predictions"]}、误改{d["harmed_predictions"]}。计数单位是试次×种子，不能当作独立受试者。')
    lines += ['', '## 数学与选参（已冻结）','',
        '源网络240维特征、原输入尺度、全部权重、BN与dense保持不动，使用原源检查点，不使用前轮BN候选。本人前80只拟合特征StandardScaler和四个残差解，80–119只选强度，>=120共同测试。源拟合不含外层目标人；个人适配是明确的有标签例外。', '',
        '`z=(features-mean_fit)/scale_fit; r=y-p_source`',
        '`min_(w,b) mean[(r-z@w-b)^2] + alpha*||w||^2`',
        '`w=Z.T@solve(Z@Z.T+n*alpha*I,r_c); b=mean(r)-mean(z)@w`',
        '`p_bounded=clip(p_source+lambda*clip(z@w+b,-0.15,+0.15),0,1)`',
        '`p_free=clip(p_source+lambda*(z@w+b),0,1)`','',
        'alpha顺序10／1／0.1／0.01；lambda顺序0.25／0.5／1。每分支先恒等，再lambda升序、alpha降序共13候选，40验证试次BA最高、并列选最先。不超过原源验证就恒等；不以测试选择、重拟合或删人。两个分支共享4个ridge解，共360个解、180个选定状态全部冻结后评分。','',
        '## 公平性和未验证边界','',
        '- 原源模型没有个人标签；旧个人头只用80拟合、没有40验证选择。残差新增40验证标签和13候选，因此不是等标签／等调参预算，不能把其分数称为零标签跨人提升。两个残差分支的预算相同。',
        '- 个人前后段共享父实验，40试次块仅原顺序代理，逐试次run身份和跨日漂移未验证。原30人及后段反复使用；旧10人／已暴露12人／原始MAT不打开。',
        '- 没有静息类和实时误触发成绩；左右手二分类分数不能授权灵巧手动作。未佩戴、未访问Z15、未导出ARM、未修改PL／服务／正式恢复包。','',
        '## 实现及审计','',
        f'- sklearn SVD Ridge重建全部{v["ridge_solutions_svd_rebuilt"]}解，最大系数绝对误差{v["max_abs_coefficient_error"]:.12g}；全部180个验证选择重建一致。系数容差rtol1e−9/atol1e−9，未放宽。',
        f'- 复算{v["predictions_recomputed"]}预测；两个新残差分支CPU／CUDA类别完全一致，旧源也重算，旧个人头CPU重建。最大分数绝对误差{v["max_abs_score_error"]:.12g}，容差rtol2e−5/atol2e−5，未放宽。',
        f'- 独立NumPy整数审计{a["integer_predictions_checked"]}预测、180个状态、训练／验证／测试索引、基线原数组、混淆矩阵、BA/F1、bootstrap、关口、限幅保护、回退和纠正／误改计数通过。',
        '- 单元测试执行数、环境、各文件摘要和完整完成状态见RUN_STATUS.md。','',
        '## 实现依据与复现','',
        '仅核对通用[Ridge／Tikhonov定义](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html)及[NumPy线性求解](https://numpy.org/doc/stable/reference/generated/numpy.linalg.solve.html)，没有从EEG/MI论文挑法，不宣称本组合首次出现。线上库版本可能较新；本机环境未升级，实际实现与本机sklearn单测及全量重建对照。','',
        f'结果SHA256：`{result_hash}`。输入／代码／模型冻结见`lock.json`、`code_snapshot/`、`source_freeze.json`；原预测见`fold_predictions/`，独立证据见`verification.json`、`integer_count_audit.json`。','',
        '在`D:/ican/codex_project/eeg_apps_z15`执行。已完成输出拒绝覆盖，重跑须隔离副本和新输出目录，审计／报告RUN同步改为新目录后重新冻结。','', '```powershell',
        r'.\.venv-mi\Scripts\python.exe -X utf8 -m unittest test_mi_residual test_mi_bn_trainonly test_mi_crossfield_stability test_mi_person_transfer test_mi_model_comparison test_cho2017_pipeline test_cho2017_adaptation',
        r'.\.venv-mi\Scripts\python.exe -X utf8 mi_residual_diagnostic.py prepare',
        r'.\.venv-mi\Scripts\python.exe -X utf8 mi_residual_diagnostic.py train',
        r'.\.venv-mi\Scripts\python.exe -X utf8 mi_residual_diagnostic.py evaluate',
        r'.\.venv-mi\Scripts\python.exe -X utf8 mi_residual_diagnostic.py verify',
        r'.\.venv-mi\Scripts\python.exe -X utf8 audit_mi_residual.py',
        r'.\.venv-mi\Scripts\python.exe -X utf8 report_mi_residual.py', '```','']
    target.write_text('\n'.join(lines),encoding='utf-8')
    print(target)


if __name__=='__main__':
    main()
