"""Report only independently verified source-validation diagnostic numbers."""
from pathlib import Path
from hashlib import sha256
import json

HERE = Path(__file__).resolve().parent
RUN = HERE/'output/mi_readout_source_diagnostic_20261002'


def main():
    target = RUN/'RESULTS.md'
    if target.exists():
        raise RuntimeError('Completed report preserved')
    p, r, v, a = [json.loads((RUN/name).read_text(encoding='utf-8')) for name in
                  ('protocol.json', 'results.json', 'verification.json', 'integer_count_audit.json')]
    result_hash = sha256((RUN/'results.json').read_bytes()).hexdigest()
    assert v['passed'] and a['passed'] and v['results_sha256'] == a['results_sha256'] == result_hash
    lines = ['# 固定八通道：同一表示的线性／受限非线性源验证诊断', '',
        '2026-10-02。F3,F4,C3,C4,T7,T8,O1,O2，左右手想象二分类；只做原30人内26源拟合／3源验证。**没有新增外层目标人成绩、ARM导出、Z15访问、PL变更或佩戴。**', '',
        '## 三个固定条件', '']
    for method, value in r['methods'].items():
        ci = value['descriptive_person95ci']
        seeds = '；'.join(f'{seed}: {100*ba:.4f}%' for seed, ba in value['seed_mean_ba'].items())
        lines.append(f'- `{method}`：{p["dimensions"][method]}维，28人等权源验证BA **{100*value["mean_person_ba"]:.4f}%**，描述性95%区间{100*ci[0]:.4f}～{100*ci[1]:.4f}%；macro-F1 {value["mean_person_f1"]:.6f}；最弱7人BA {100*value["mean_lowest7_ba"]:.4f}%。')
        lines.append(f'  源拟合人BA（重复折的描述性均值）{100*value["descriptive_source_fit_mean_ba"]:.4f}%；种子源验证均值 [{seeds}]，种子均值SD {100*value["seed_mean_sd"]:.4f}个百分点。')
    lines += ['', 'LINEAR为旧WHOLE30份模型逐位复用，seed0只是确定性哨兵；其余各90份新模型按42/43/44三种子逐人等权平均。不是最佳种子，也不是预测投票／分数集成的准确率。',
        f'源验证28名不同人（14、28未出现），每种子90个人员出现、单人1～7次；{r["unique_validation_trials"]}唯一试次、{r["unique_validation_author_flags"]}作者异常标记保留。全部{r["total_predictions"]}预测：基线18,280，两个扩展各54,840。不能与旧外层63.83%／64.25%直接比较。', '',
        '## 评分前锁定的共同主要关口', '',
        'RFF−LINEAR平均增益至少2个百分点；RFF−LINEAR_PROJECTED至少1个百分点；二者各自名义Bonferroni覆盖97.5%的描述性人员配对区间下限>0，最弱7人均值下降≤1个百分点。全部满足才提名下一轮另锁比较，不晋升。', '']
    for name, value in r['comparisons'].items():
        ci = value['descriptive_paired_ci']
        role = ('共同主要关口通过' if value['direction_gate'] else '共同主要关口未通过') if value['co_primary'] else '描述性、不选赢家'
        lines.append(f'- `{name}`：差{100*value["mean_gain"]:+.4f}个百分点，描述性{100*value["nominal_coverage"]:.1f}%配对区间{100*ci[0]:+.4f}～{100*ci[1]:+.4f}；最弱7人差{100*value["lowest7_mean_difference"]:+.4f}；{value["people_improved"]}人提高／{value["people_declined"]}人下降；{role}。')
    lines += ['', '## 决策和边界', '',
        ('两项共同主要关口均通过；只支持另锁下一轮有限比较，不构成独立外层改善、真实Cyton准确率或部署授权。' if r['nominate_for_later_locked_comparison'] else '至少一项共同主要关口未通过，本固定非线性配方不进入外层评分或板端部署。不追加gamma／C／维度／种子搜索，不用最高种子或描述性控制顶替主要候选。'),
        '源拟合／验证落差仅描述本轮表示、容量、正则和数据的共同影响，不能唯一认定非线性／信号质量／佩戴或某道预处理是原因。失败不证明所有非线性方法无效；本轮非线性也不恢复WHOLE已抹去的绝对幅值或时间顺序。',
        '源验证已经多轮开发，训练集合高度重叠；人员bootstrap是描述性区间，名义多重比较校正不创造独立确认。最弱7人各方法独立排序，未必同7人。', '', '## 相同输入与受限映射', '',
        '- 仅原2秒8–30Hz、CAR、迹归一化、0.05正定化36维WHOLE；未挑上轮分频分支，没有新增原始EEG或滤波。',
        '- 仅26源人StandardScaler。LINEAR使用z。两扩展用原块z/sqrt(2)，附加块减源均值、乘源标量sqrt(18/源平均平方范数)；两块源范数各18、总36，验证不重新拟合统计。',
        '- 128个固定随机分量，gamma=1/72，种子42/43/44。LINEAR_RFF用sqrt(2/128)cos(zW+b)；LINEAR_PROJECTED用同W的zW/sqrt(128)，仍是原空间仿射函数。三条件维数36／164／164，分类系数37／165／165，并非容量相同。固定映射W、b不学习，归一化标量／均值也须保存。',
        '- RFF块被源中心化／缩放并与线性块相加，属于固定混合表示，不称精确RBF SVM。三个种子共享所有30折的各自W、b，不能挑最优映射。',
        '- 30基线逐位复用；180新增L2 logistic固定C=0.1、tol1e−10、maxiter1000，整体210状态冻结后才评分；没有C／gamma／维数搜索或验证选择检查点。',
        '- 每折自己的外层人不在源拟合或源验证。原30人的标签无关缓存全行可读，不声称未读任何外层波形；另22人EEG和原始MAT未读。旧12人已暴露，不能再次当盲确认。', '', '## 独立验算', '',
        f'- 全{v["schur_waveforms_rebuilt"]}行另以Schur logm重建，最大特征误差{v["max_feature_error"]:.12g}；RandomState独立重建随机图，复数指数／einsum复算映射及源统计，最大映射误差{v["max_transform_error"]:.12g}。',
        f'- {v["independent_solutions"]}个独立解析解、{v["predictions_recomputed"]}源验证预测全部通过；类别完全一致。最大系数／分数误差{v["max_coefficient_error"]:.12g}／{v["max_score_error"]:.12g}；最大最终梯度{v["max_gradient"]:.12g}。其中{v["solutions_refined"]}个解按预声明残差修正，不改原权重、分数或容差。',
        '- 独立NumPy审计人员／种子／出现次数加权、指标、区间、门槛、源训练指标、外层排除、源统计、原基线预测数组一致性；测试和冻结时刻见RUN_STATUS.md。', '', '## 通用来源与复现', '',
        '[scikit-learn Kernel Approximation](https://scikit-learn.org/stable/modules/kernel_approximation.html)、[RBFSampler](https://scikit-learn.org/stable/modules/generated/sklearn.kernel_approximation.RBFSampler.html)说明通用随机特征映射。实际使用本机1.4.2且核对源码，不安装新库。不是EEG首次性证明，也没有保证70%。',
        f'结果SHA256：`{result_hash}`。代码快照、maps、models、validation_predictions保留，不覆盖。复现需新隔离目录并在运行前调整／锁定全部输出路径。', '',
        '工作目录：D:/ican/codex_project/eeg_apps_z15。', '', '```powershell',
        '.\\.venv-mi\\Scripts\\python.exe -X utf8 mi_readout_diagnostic.py prepare',
        '.\\.venv-mi\\Scripts\\python.exe -X utf8 mi_readout_diagnostic.py train',
        '.\\.venv-mi\\Scripts\\python.exe -X utf8 mi_readout_diagnostic.py evaluate',
        '.\\.venv-mi\\Scripts\\python.exe -X utf8 mi_readout_diagnostic.py verify',
        '.\\.venv-mi\\Scripts\\python.exe -X utf8 audit_mi_readout.py',
        '.\\.venv-mi\\Scripts\\python.exe -X utf8 report_mi_readout.py', '```', '']
    target.write_text('\n'.join(lines), encoding='utf-8')
    print(target)


if __name__ == '__main__':
    main()
