"""Only source-validation diagnostic claims from independently audited arrays."""
from pathlib import Path
import json
import hashlib

RUN=Path(__file__).resolve().parent/'output/mi_time_frequency_source_diagnostic_20261002'


def main():
    target=RUN/'RESULTS.md'
    if target.exists():raise RuntimeError('Completed report preserved')
    p,r,v,a=[json.loads((RUN/name).read_text(encoding='utf-8')) for name in
        ('protocol.json','results.json','verification.json','integer_count_audit.json')]
    result_hash=hashlib.sha256((RUN/'results.json').read_bytes()).hexdigest()
    assert v['passed'] and a['passed'] and v['results_sha256']==a['results_sha256']==result_hash
    main_comparison=r['comparisons']['TIME2_FREQ2_minus_WHOLE']
    lines=['# 固定八通道：时间／频率压缩的源验证诊断','','2026-10-02，仅原30人的26源拟合／3源验证划分。左右手二分类，帽位`F3,F4,C3,C4,T7,T8,O1,O2`不变。**本轮没有计算新的外层目标人成绩，没有移植、佩戴或控制命令。**','','## 四个固定条件','']
    for method,m in r['methods'].items():
        lo,hi=m['descriptive_person95ci']
        lines.append(f'- `{method}`，维数{p["dimensions"][method]}：28名源验证人的等权平均BA **{100*m["mean_person_ba"]:.4f}%**；描述性95%人员区间{100*lo:.4f}～{100*hi:.4f}%；macro-F1 {m["mean_person_f1"]:.6f}；最弱7人均值{100*m["mean_lowest7_ba"]:.4f}%。')
    lines+=['',f'源验证共有90个人员出现、28名不同人（14、28没有出现），各人出现1～7次。先平均同人各出现的BA，再平均28人；不是90个独立人。{r["unique_validation_trials"]}唯一源验证试次、{r["unique_validation_author_flags"]}作者异常标记全部保留；每条件{r["predictions_per_method"]}预测，总{r["total_predictions"]}预测。',
        '这些成绩不能与旧外层后段64.25%／59.43%直接相减：人群、时间分母和角色不同，验证集合已被此前开发使用。训练集合重叠，人员bootstrap只描述当前数据的差异，不证明独立跨人提升。','','## 预声明主要线索关口','',
        '主要比较仅TIME2_FREQ2减WHOLE。增益≥2个百分点、描述性95%人员配对区间下限>0、最弱7人均值下降≤1个百分点须同时满足；通过只建议下一轮另锁协议比较，不晋升。4项描述性比较不得替代主比较。','']
    for name,c in r['comparisons'].items():
        lo,hi=c['descriptive_paired_ci']
        label=('主要线索通过' if c['direction_gate'] else '主要线索未通过') if c['primary'] else '描述性'
        lines.append(f'- `{name}`：差{100*c["mean_gain"]:+.4f}个百分点，描述性95%配对区间{100*lo:+.4f}～{100*hi:+.4f}；最弱7人差{100*c["lowest7_mean_difference"]:+.4f}；{c["people_improved"]}人提高／{c["people_declined"]}人下降；{label}。')
    lines+=['','## 判断与局限','',
        ('联合分解达到预声明源验证线索关口。下一步可另锁一次有限外层比较，仍不能称为已提高最终准确率、达70%或可上板。' if main_comparison['direction_gate'] else '联合分解未达到预声明源验证线索关口，不把它升级为新的板端模型，也不挑描述性分支代替主候选。'),
        '验证的最弱7人各方法独立排序，未必是同7人。频率、时间分解改变了维数和短段协方差估计；固定sqrt(36/d)标准化后缩放只匹配源平均平方范数，不匹配信息容量／自由度。任何增益都不能唯一证明此前错误来自某个处理环节。',
        'WHOLE不保留样本时间顺序已由标签无关的重排不变性验证；这证明表示具有该性质，不等于丢失的信息必然与左右手标签相关。没有清醒／疲劳、情绪、静息或误触发验证。','','## 固定计算与边界','',
        '- WHOLE：整个2秒。TIME2：前后各1秒。FREQ2：在完成2秒窗口的实DFT上按<14Hz／≥14Hz互补划分。联合：先整窗分频，再各分前后两段；不重采样、不重排真实试次，不在每半窗重复FFT。',
        '- 输入仍为既有8–30Hz缓存，但互补频率保留全部频点及残留；不称严格8–14／14–30Hz带通。FFT完成窗口、周期边界和非因果性只属于诊断，不声称连续滤波或板端等价。',
        '- 分量协方差均除同一父迹，保留相对能量；绝对父幅值消除。既有0.05相对迹正定化、矩阵对数、sqrt(2)上三角实现不改。WHOLE与上轮特征全6080行对照一致。',
        '- 26源人拟合StandardScaler，变换后乘sqrt(36/d)；4条件全部C=0.1，lbfgs tol1e−10/max_iter1000，无频点／时间／C网格，无验证选模。120确定性模型整体冻结后才统一源验证评分。',
        '- 每一折的外层目标人都不在自己的训练／验证列表。其他人的试次在其他折属于合法源数据；不要把固定无标签全6080行特征预计算说成未访问任何外层波形。',
        '- 未打开旧10人／已暴露12人EEG或原始MAT；未导出ARM、访问Z15、改PL／启动服务／正式恢复包或发送执行器命令。已有12人不再盲封存，本轮不是独立确认。','','## 独立复核','',
        f'- SciPy FFT＋Schur logm重建{v["schur_fft_waveforms_rebuilt"]}个波形的全部{v["log_matrices_rebuilt"]}矩阵；最大特征误差{v["max_feature_error"]:.12g}。',
        f'- 解析trust-exact＋预声明Newton残差修正独立重建{v["independent_solutions"]}个解，其中{v["solutions_refined"]}个修正；最大梯度{v["max_gradient"]:.12g}，最大系数误差{v["max_coefficient_error"]:.12g}，没有放宽原声明。',
        f'- 复算全部{v["predictions_recomputed"]}源验证预测，类别完全一致，最大分数误差{v["max_score_error"]:.12g}。独立NumPy计数审计所有源索引／外层排除、参数、人员重复加权、混淆矩阵、BA/F1、描述性区间和线索关口通过。',
        '- 全6080个WHOLE时间重排不变性、频率互补恢复和正交交叉协方差通过；单测／完整环境／冻结时刻见RUN_STATUS.md，原始模型、预测和代码快照分别在models、validation_predictions、code_snapshot。','','## 通用依据与实际命令','',
        '[NumPy rfft](https://numpy.org/doc/stable/reference/generated/numpy.fft.rfft.html)和[irfft](https://numpy.org/doc/stable/reference/generated/numpy.fft.irfft.html)提供通用实FFT／逆变换定义；本机NumPy2.4.6未升级。仅实现参考，不是EEG新颖性或识别效果证据。',
        f'结果SHA256：`{result_hash}`。现有输出拒绝覆盖，复现须新隔离目录及提前更新路径／锁定，不直接覆盖证据。','',
        '在`D:/ican/codex_project/eeg_apps_z15`执行：','','```powershell',
        r'.\.venv-mi\Scripts\python.exe -X utf8 -m unittest test_mi_time_frequency test_mi_logcov_verification test_mi_logcov test_mi_residual test_mi_bn_trainonly test_mi_crossfield_stability test_mi_person_transfer test_mi_model_comparison test_cho2017_pipeline test_cho2017_adaptation',
        r'.\.venv-mi\Scripts\python.exe -X utf8 mi_time_frequency_diagnostic.py prepare',
        r'.\.venv-mi\Scripts\python.exe -X utf8 mi_time_frequency_diagnostic.py train',
        r'.\.venv-mi\Scripts\python.exe -X utf8 mi_time_frequency_diagnostic.py evaluate',
        r'.\.venv-mi\Scripts\python.exe -X utf8 mi_time_frequency_diagnostic.py verify',
        r'.\.venv-mi\Scripts\python.exe -X utf8 audit_mi_time_frequency.py',
        r'.\.venv-mi\Scripts\python.exe -X utf8 report_mi_time_frequency.py','```','']
    target.write_text('\n'.join(lines),encoding='utf-8');print(target)


if __name__=='__main__':main()
