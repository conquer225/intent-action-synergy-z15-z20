# 固定八通道：训练数据BN重估对照

2026-10-02。检验上一轮“小样本检查点归一化更新偏少”的线索。假设：保持权重不变，训练数据重估运行统计可使本人80试次模型平均BA提高至少3个百分点且校正配对区间下限>0；若未达到，则不能把BN统计不足当作具有实际收益的解释。源模型另设至少1个百分点的继续研究关口，沿用此前低幅改善不晋升的边界；不据这个开发关口部署。

## 不变范围

只用原30人的6080试次缓存、固定`F3,F4,C3,C4,T7,T8,O1,O2`、左右手二分类、种子42/43/44、原始7秒试次处理及0.5–2.5秒窗口。同一后段order>=120共2480试次，每条件7440预测。上一轮原模型该分母为63.3843%，不能直接使用其他起点的63.83%。原30人和既往源BN结果已暴露，本轮是明确的探索性机制检查，不是盲独立确认，也不消除反复开发的选择偏差。

不重新训练或选择权重，不调早停、滤波、窗、batch或通道，不重训个人LDA头。个人分类头依赖原特征；改变BN后继续使用旧头会混入另一种不匹配，因此它不参与本轮纯BN对照。

## 三组配对对照

1. `CROSS_ORIGINAL` / `CROSS_SOURCE_BN`：原26人源模型；只用对应26名拟合人的全部训练试次重估，排除3名源验证人和目标人。
2. `PERSON_ONLY` / `PERSON_BN`：上一轮本人前80试次训练的原检查点；只用同一前80试次重估，不使用80–119验证段或>=120测试段。
3. `CROSS_MATCHED80` / `MATCHED80_BN`：上一轮冻结的80跨人拟合索引；不重新抽样，不加入40验证试次或目标人。

沿用已测试的`mi_crossfield_stability.recalibrate_bn`：batch256、原索引升序、仅一遍、无标签输入。先全部eval以关闭Dropout，清空BN运行统计，BN临时train且momentum=None，完成后恢复原momentum并全部eval。只允许running_mean/running_var/num_batches_tracked变动；包括BN仿射参数的所有可学习张量、标准化均值尺度都须逐位相同。

这里是PyTorch累计批次统计：每批等权，最后短批也等权；后级BN看到的是前级按当前批归一化的激活。不是逐层全训练集精确总体矩，也不声称比现有处理方法创新。仅核查通用训练机制，没有从EEG论文选新算法。

## 冻结、评分与规则

先冻结协议、代码、原结果/模型/划分及270个新重估状态，再统一评分。两项主要比较（源BN对原源模型；本人BN对本人原模型）使用97.5%受试者配对bootstrap区间，分别要求>=1/3个百分点且下限>0。匹配预算BN对原匹配预算、本人的BN对原跨人为95%描述性比较；不得事后改成主要候选或挑最佳种子。

先对每人三种子平均，再对30人等权平均。保留全部人物、试次与异常标记，报告BA、macro-F1、跨人SD、最弱8人均值、混淆矩阵、逐人逐种子预测。个人分块共享父实验是明确诊断例外；个人收益不能称为零校准跨人收益。

CPU重建全部270个BN状态；所有权重/尺度严格相同，BN容差rtol2e−5/atol2e−6；复算六条件44640预测，类别必须相同、分数容差rtol2e−5/atol2e−5。用独立NumPy实现复核整数混淆矩阵、聚合、区间、阈值、分母和划分。若失败先检查实现，不通过放宽容差或删低分试次使其通过。

```powershell
.\.venv-mi\Scripts\python.exe -X utf8 -m unittest test_mi_bn_trainonly test_mi_crossfield_stability test_mi_person_transfer test_mi_model_comparison test_cho2017_pipeline test_cho2017_adaptation
.\.venv-mi\Scripts\python.exe -X utf8 mi_bn_trainonly.py prepare
.\.venv-mi\Scripts\python.exe -X utf8 mi_bn_trainonly.py calibrate
.\.venv-mi\Scripts\python.exe -X utf8 mi_bn_trainonly.py evaluate
.\.venv-mi\Scripts\python.exe -X utf8 mi_bn_trainonly.py verify
.\.venv-mi\Scripts\python.exe -X utf8 audit_mi_bn_trainonly.py
.\.venv-mi\Scripts\python.exe -X utf8 report_mi_bn_trainonly.py
```

不读取旧10人或12人的EEG，不打开原始MAT、不佩戴、不访问Z15、不导出ARM模型、不操作PL/正式服务/执行器。正式恢复包摘要须保持不变。
