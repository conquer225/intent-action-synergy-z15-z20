"""Render immutable audited energy diagnostic results as Markdown."""
from mi_energy_diagnostic import RUN, read, digest


def main():
    path = RUN/'RESULTS.md'
    if path.exists():
        raise RuntimeError('Existing report preserved')
    p, result, verification, audit = [read(RUN/name) for name in
        ('protocol.json', 'results.json', 'verification.json', 'integer_count_audit.json')]
    assert verification['passed'] and audit['passed']
    result_hash = digest(RUN/'results.json')
    assert verification['results_sha256'] == audit['results_sha256'] == result_hash
    text = ['# 固定八通道：绝对能量信息保留／去除源验证诊断', '',
        '2026-10-02。F3,F4,C3,C4,T7,T8,O1,O2、左／右手想象，原30人内部26源拟合／3源验证。没有新增外层目标评分，不佩戴、不访问Z15、不导出ARM、不修改PL或正式服务。', '',
        '## 固定三条件与源验证结果', '']
    for method in p['methods']:
        metric = result['methods'][method]
        ci = metric['descriptive_person95ci']
        text += [f"- `{method}`（{p['dimensions'][method]}维）：人员等权源验证BA **{metric['mean_person_ba']*100:.4f}%**，描述性95%区间{ci[0]*100:.4f}～{ci[1]*100:.4f}%；macro-F1 {metric['mean_person_f1']:.6f}；最弱7人BA {metric['mean_lowest7_ba']*100:.4f}%。源拟合描述性BA {metric['descriptive_source_fit_mean_ba']*100:.4f}%。"]
    text += ['', '28名源验证人，14、28未出现；同人1～7次先平均，再28人等权。90次人员出现，5680唯一试次、510作者异常标记保留。三条件共54840次预测，不是新的盲独立跨人测试、本人实时准确率，不能与旧外层63.83%／64.25%直接相减。', '',
        '## 评分前声明的比较与决策', '',
        '唯一主要比较NORMALIZED_ENERGY−NORMALIZED：均值至少+2个百分点、描述性95%人员配对区间下限>0、最弱7人下降≤1个百分点。其余只是描述性控制，不能替换主要候选。', '']
    for comparison, row in result['comparisons'].items():
        ci = row['descriptive_paired_ci']
        status = ('通过' if row['direction_gate'] else '未通过') if row['primary'] else '描述性，不选赢家'
        text += [f"- `{comparison}`：差{row['mean_gain']*100:+.4f}个百分点；描述性95%区间{ci[0]*100:+.4f}～{ci[1]*100:+.4f}；最弱7人差{row['lowest7_mean_difference']*100:+.4f}；{row['people_improved']}人提高／{row['people_declined']}人下降；{status}。"]
    primary = result['comparisons']['NORMALIZED_ENERGY_minus_NORMALIZED']
    decision = ('仅提名另锁比较，不部署。' if primary['direction_gate'] else '主要改善关口未通过，停止本能量配方及当前诊断分支，不追参数或新增外层评分。')
    text += ['', decision, '',
        '## 计算定义和公平性边界', '',
        'S是原8×500去时间均值无偏协方差；t=trace(S)，u=ln(t)，原N=vec_upper(log(S/t+0.05I/8))，非对角乘sqrt(2)。原N36维逐位复用；主要候选[N,u]37维；ABSOLUTE=N+u·vec(I)36维，数学上等于vec(log(S+0.05tI/8))。没有修改滤波、参考、频带、事件窗口或原始采集。', '',
        '每条件StandardScaler只拟合26源人，factor=1。主要候选原36列统计保持不变，只加1标准化能量列。源平均平方范数36／37／36、系数含截距37／38／37，不是同容量对照；ABSOLUTE混合尺度与形状，改变正则几何。原30份WHOLE状态NPZ逐位复用，60个新L2 logistic固定C=0.1，90状态整体冻结后才评分，无网格、种子选择或验证选参。', '',
        '能量单位来自原缓存，不声称已统一Cyton物理单位。统一单位倍乘可被源标准化吸收，但不同人增益、参考或伪迹仍会混淆能量。没有基线相对ERD，不恢复样本顺序。数学上保留／丢弃能量已验证，不等于证明它是识别瓶颈。失败也不能证明所有能量方法、固定帽位或真实佩戴无效。', '',
        '原源验证已重复开发、源训练集合高度重叠；人员bootstrap仅描述当前数据，不是新的独立确认。最弱7人各方法独立排序，未必同7人。另22人EEG及原始MAT未读，旧12人已经暴露，不能再次称盲确认。', '',
        '## 独立验算与证据', '',
        f"- 6080行另用np.cov/trace与Schur logm重建12160张矩阵，最大特征误差{verification['max_feature_error']:.12g}。全部6080行幅值乘2的恒等探针通过。",
        f"- 90个独立解析解、54840预测类别全部一致。最大系数／分数误差{verification['max_coefficient_error']:.12g}／{verification['max_score_error']:.12g}；最大最终梯度{verification['max_gradient']:.12g}。{verification['solutions_refined']}解用预声明残差修正，没有修改原权重、分数或容差。",
        '- 独立NumPy审计源统计、试次身份、原基线状态与预测数组、外层排除、源训练指标、整数混淆矩阵、人员重复加权、区间和关口全部通过。完整测试和冻结时刻见RUN_STATUS.md；交付摘要见delivery_checks.json。',
        '- 原6080身份和515作者异常标记保留。正式恢复包SHA不变，本轮没有板端操作、执行器或启动文件变更。', '',
        f'结果SHA256：`{result_hash}`。协议、源码快照、模型、逐折预测和solver_trace一并保留。现有输出拒绝覆盖；复现需新隔离目录，并提前调整和锁定全部输出路径。', '',
        '## 命令', '', '工作目录D:/ican/codex_project/eeg_apps_z15。', '', '```powershell',
        '.\\.venv-mi\\Scripts\\python.exe -X utf8 mi_energy_diagnostic.py prepare',
        '.\\.venv-mi\\Scripts\\python.exe -X utf8 mi_energy_diagnostic.py train',
        '.\\.venv-mi\\Scripts\\python.exe -X utf8 mi_energy_diagnostic.py evaluate',
        '.\\.venv-mi\\Scripts\\python.exe -X utf8 mi_energy_diagnostic.py verify',
        '.\\.venv-mi\\Scripts\\python.exe -X utf8 audit_mi_energy.py',
        '.\\.venv-mi\\Scripts\\python.exe -X utf8 report_mi_energy.py', '```', '']
    path.write_text('\n'.join(text), encoding='utf-8')
    print(path)


if __name__ == '__main__':
    main()
