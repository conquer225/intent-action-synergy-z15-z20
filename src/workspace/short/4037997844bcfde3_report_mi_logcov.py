"""Report only audited source-only log-covariance scores, no model promotion."""
from pathlib import Path
import json
import hashlib

RUN=Path(__file__).resolve().parent/'output/mi_logcov_sourceonly_20261002'


def main():
    target=RUN/'RESULTS.md'
    if target.exists():raise RuntimeError('Completed report preserved')
    p,r,v,a=[json.loads((RUN/name).read_text(encoding='utf-8')) for name in ('protocol.json','results.json','verification.json','integer_count_audit.json')]
    result_hash=hashlib.sha256((RUN/'results.json').read_bytes()).hexdigest()
    assert v['passed'] and a['passed'] and v['results_sha256']==a['results_sha256']==result_hash
    lines=['# 固定八通道：完整空间矩阵对数源训练对照','','2026-10-02，Cho2017原30人重复开发，左右手二分类。八位置`F3,F4,C3,C4,T7,T8,O1,O2`不变；所有方法使用目标人标签0个。不是独立确认、跨日、Cyton或新颖性证据。','','## 结果','']
    for method,m in r['methods'].items():
        lo,hi=m['person95ci']
        lines.append(f'- `{method}`：人员平均BA **{100*m["mean_person_ba"]:.4f}%**，95%区间{100*lo:.4f}～{100*hi:.4f}%；macro-F1 {m["mean_person_f1"]:.6f}；人员SD{100*m["between_person_sd"]:.4f}个百分点；最弱8人均值{100*m["mean_lowest8_ba"]:.4f}%。')
    lines+=['','共同2480唯一后段试次、198作者异常试次全保留。两个源EEGNet各三种子先逐人平均；两个新模型各为确定性一条，不重复三次充当随机种子。共19840预测、240预测文件；新条件各2480预测，参考各7440。旧63.83%的测试起点不同，不直接相减。','','## 预声明判定','','主要比较仅完整矩阵减更强源BN参考：平均增益≥2个百分点，95%人员配对bootstrap下限>0，最弱8人均值下降≤1个百分点，三项同时满足。其他比较只描述，不能事后替代主要候选。人员bootstrap10000次、seed20261002；本轮一项主要比较，但多轮开发偏差仍存在。','']
    for name,c in r['comparisons'].items():
        lo,hi=c['paired_ci'];verdict=('主要通过' if c['development_gate'] else '主要未通过') if c['primary'] else '描述性'
        lines.append(f'- `{name}`：差{100*c["mean_gain"]:+.4f}个百分点，95%配对区间{100*lo:+.4f}～{100*hi:+.4f}；最弱8人差{100*c["lowest8_mean_difference"]:+.4f}个百分点；{c["people_improved"]}人提高／{c["people_declined"]}人下降；{verdict}。')
    primary=r['comparisons']['LOGCOV_FULL_LR_minus_CROSS_SOURCE_BN']
    lines+=['','## 是否晋升','',('达到开发关口，可考虑另一次独立设计和移植验证，仍未授权上线。' if primary['development_gate'] else '本配方未达到开发关口，不晋升、不改C网格／正则／频带／测试起点追分，也不挑对角对照上线。'),'这只能检验本次固定矩阵对数＋线性配方，不能证明所有空间特征无效、固定帽位无效或找到唯一失败原因。','','## 固定实现与预算','','- 原波形滤波／帽位／500样本不变。单试次中心化协方差除自身迹，再加`0.05*I/8`，矩阵对数、sqrt(2)加权上三角共36维。复用既有数学函数，处理CAR低秩；不学习目标人参考矩阵。',
        '- 对角消融为同一矩阵对数8个对角项，仍与整矩阵有关，不是独立通道log功率。36维／8维容量不同，不能声称同容量。',
        '- 每折只在同26源人拟合StandardScaler与L2 logistic；同3源人选择C=0.01/0.1/1/10，源验证逐人等权BA，并列更强正则；不合并验证人再拟合。lbfgs tol1e−10、max_iter1000，收敛警告作为错误。',
        '- 总240确定性拟合、60选定状态先冻结再目标评分。固定无标签单试次特征在拟合前已提取，不把冻结后的评分标记冒充首次波形访问。',
        '- 原30人及后段已反复开发。旧10人、已暴露12人和原始MAT未打开；前120未评分不代表使用其个人标签校准。新4次C选择与原神经epoch选择不同，不称等计算／调参预算。',
        '- 项目以前已有GAMEEMO及PhysioNet矩阵对数；本次是在当前Cho2017固定划分中测试，不宣称创新首次出现。',
        '- 没有静息类、误触发、本人MI、ARM耗时或PL加速证据。不佩戴、不访问板卡、不导出ARM／改PL或启动服务，不发送执行器命令。','','## 独立复核','',
        f'- Schur矩阵对数重建全部{v["schur_features_rebuilt"]}特征行，最大误差{v["max_feature_error"]:.12g}；不只在小样本检查。',
        f'- 显式sum-logloss+L2解析梯度／Hessian、scipy trust-exact独立重建{v["independent_newton_solutions"]}解；60个源验证选择全部一致。最大系数误差{v["max_coefficient_error"]:.12g}、最大梯度无穷范数{v["max_independent_gradient"]:.12g}。',
        f'- 复算{v["predictions_recomputed"]}预测，类别完全一致，最大分数误差{v["max_score_error"]:.12g}；新分支和原参考使用各自预声明容差，没有评分后放宽。',
        '- 独立NumPy整数审计不导入Torch、不拟合：全部训练／验证／目标索引、240个验证候选的人员混淆矩阵、60个选择、原参考数组、BA/F1/人员bootstrap/门槛通过。',
        '- 单测数、环境、冻结时刻和完成状态见RUN_STATUS.md；模型参数及选择轨迹见models/；输入摘要见lock.json，全部脚本快照见code_snapshot/。','','## 通用依据与复现','',
        '[SciPy矩阵对数](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.logm.html)；[sklearn1.4 LogisticRegression](https://scikit-learn.org/1.4/modules/generated/sklearn.linear_model.LogisticRegression.html)。仅通用数学／软件依据，不代表该配方在EEG里首次使用或必然提高准确率。没有安装／升级依赖。',
        f'结果SHA256：`{result_hash}`。机器证据：results.json、verification.json、integer_count_audit.json。','',
        '在`D:/ican/codex_project/eeg_apps_z15`执行；已完成输出拒绝覆盖，重跑需要隔离副本、新输出目录以及审计／报告路径更新，再锁定后执行。','','```powershell',
        r'.\.venv-mi\Scripts\python.exe -X utf8 -m unittest test_mi_logcov test_mi_residual test_mi_bn_trainonly test_mi_crossfield_stability test_mi_person_transfer test_mi_model_comparison test_cho2017_pipeline test_cho2017_adaptation',
        r'.\.venv-mi\Scripts\python.exe -X utf8 mi_logcov_comparison.py prepare',
        r'.\.venv-mi\Scripts\python.exe -X utf8 mi_logcov_comparison.py train',
        r'.\.venv-mi\Scripts\python.exe -X utf8 mi_logcov_comparison.py evaluate',
        r'.\.venv-mi\Scripts\python.exe -X utf8 mi_logcov_comparison.py verify',
        r'.\.venv-mi\Scripts\python.exe -X utf8 audit_mi_logcov.py',
        r'.\.venv-mi\Scripts\python.exe -X utf8 report_mi_logcov.py','```','']
    target.write_text('\n'.join(lines),encoding='utf-8');print(target)


if __name__=='__main__':main()
