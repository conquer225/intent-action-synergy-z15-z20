# 固定八通道：个人可分性与跨人迁移诊断

2026-10-02，原30人范围内的探索性诊断。此计划在本轮新模型拟合与评分前冻结。不是新的独立确认，不能改写上一轮负结果。

## 数据结构边界

Cho2017作者数据论文“Experimental design / Experiment and datasets”、Figure2与Table1说明同次实验中进行5或6轮，左右各20试次/轮。现有缓存是独立7秒试次，作者trial_sequence只恢复原顺序。30人共6080试次；每连续40试次实际均20左/20右。

已验证：原顺序、唯一身份、每40试次类别数量。合理推断：40试次块与实验轮次相符。未验证：逐试次真正run标签、真实连续时间、跨日/跨记录身份。因此报告只能称“同次实验的按原顺序分块、前段训练后段测试”，不得写成跨日或独立跨记录验证。此次只阅读数据论文的采集设计，不从EEG/MI论文选算法。

## 一次性比较

- PERSON_ONLY：本人原顺序0–79共80试次拟合通道标准化和原EEGNet，80–119共40试次仅用于早停/中心选择。保留原网络2226参数、Adam、batch64、最大200epoch、20epoch耐心、种子42/43/44。首次严格改善选择，平局取最早。
- CROSS_ORIGINAL：原26拟合人、3源验证人的原90个已审计模型/预测，不再拟合；仅在本轮相同测试索引上重新聚合。禁止直接用此前所有order>=60的63.83%作为本轮配对参考。
- SOURCE_PERSON_HEAD：固定上述原模型的输入标准化、特征提取层及BN；CPU提取dense前240维。用本人前80试次拟合特征StandardScaler和LDA（lsqr、auto收缩）分类头。无参数搜索，不用本人40验证试次选择头；头替换了原dense分类器，是不同读出器，不是原网络训练的复现。用于判断固定源表示是否能被有标签的本人读出利用。
- CROSS_MATCHED80：从同一原折26个拟合人按人/类别均匀分配80试次（每类40），从3个源验证人同理40试次（每类20）。与PERSON_ONLY相同模型和标量样本预算；标签、选择人员与时序结构不同，仍非完全因果控制。

统一测试本人原顺序>=120的所有剩余试次；200试次的人测试80，240试次的人测试120，共2480试次，三种子每方法7440个预测。本人早期有标签数据不属于“不需校准的跨人预测”。同人分块与跨人划分是诊断例外，不能作为最终跨人泛化成绩。

所有270个新模型/头（180个神经拟合、90个线性头）都先冻结，再统一前向后段测试。原始12名已暴露确认人和旧10名开发人的EEG不读取。使用完整原30人缓存，不打开原始MAT，不改滤波/窗/帽位，不按作者坏标记删人/删试次；匹配预算抽样的未使用试次仍留在总身份审计中。

## 指标和改变研究方向的规则

先对每人三种子BA平均，再按30人等权平均；报告macro-F1、SD、最弱8人均值、每人结果。PERSON_ONLY和SOURCE_PERSON_HEAD分别相对CROSS_ORIGINAL为两项预声明诊断比较，须平均提高>=5个百分点且两比较校正的97.5%按人配对bootstrap区间下限>0，才称“此标注预算下存在可观个人适配空间”。

PERSON_ONLY对CROSS_MATCHED80、SOURCE_PERSON_HEAD对PERSON_ONLY为描述性消融，95%配对区间，不另挑赢家，不使诊断变成晋升。若个人分数仍低，结论仅为“这些模型与80标签预算没有取得可靠收益”，不能断言脑电不可分或帽位无效。若高，只证明同次实验的有标签个人化；不能当作零校准跨人改善，也不能决定帽位/板端配置。

源文件、协议、数据、所有旧参考模型/预测哈希；90折种子案例的具体训练/验证/测试索引；每epoch选择历史；每试次标签、预测、分数；CPU数值与独立整数计数均保存。正式恢复包哈希保持不变。

复现入口（原运行记录，已有结果不可覆盖）：

```powershell
.\.venv-mi\Scripts\python.exe -X utf8 -m unittest test_mi_person_transfer
.\.venv-mi\Scripts\python.exe -X utf8 mi_person_transfer_diagnostic.py prepare
.\.venv-mi\Scripts\python.exe -X utf8 mi_person_transfer_diagnostic.py train
.\.venv-mi\Scripts\python.exe -X utf8 mi_person_transfer_diagnostic.py evaluate
.\.venv-mi\Scripts\python.exe -X utf8 mi_person_transfer_diagnostic.py verify
.\.venv-mi\Scripts\python.exe -X utf8 audit_mi_person_transfer_counts.py
```

本轮不授权ARM导出、板卡服务、PL、佩戴或执行器操作。
