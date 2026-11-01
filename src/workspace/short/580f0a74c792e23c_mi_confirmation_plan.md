# 左右手二分类：封存12人一次性确认

2026-10-01。用户已要求执行这项确认，通过后再做 ARM 移植和耗时核对；不要求佩戴、不改正式服务或 PL。

当前候选是未增强的小型 EEGNet，2226参数。历史30人内LOSO平均BA63.83%只用于候选筛选。本轮检验它能否在12名未参与选模的受试者上保留绝对性能与对固定B1的改善。协议 `mi_confirmation_protocol.json` 在下载／读取确认EEG前锁定；代码、源数据文档、缓存和正式恢复包哈希同时归档。

原30训练人按 SHA256(`mi-confirmation-20261001:人员编号`) 原始digest排序，前三人为验证人20、32、50，余27人为拟合。原10开发人完全排除。确认人固定为9、13、15、16、17、22、27、30、33、38、48、51。先只读取原30人缓存，完成三种子42/43/44训练和B1拟合、冻结检查点；之后才提取确认EEG。不会在确认后重训或把源验证人加入拟合。

所有模型、窗口、八路CAR、滤波、标准化、最大200epoch、patience20、源验证早停及参数约束沿用已选方案。B1与神经模型拟合人员相同；B1需每个目标前60个无标签试次建立对齐，而EEGNet无需目标适配。所有条件只评分原顺序第61个及以后试次，保留全部作者异常标记和弱人员。主指标先在每人内平均三个种子BA，再12人等权平均；它不是三模型投票或挑最佳种子。

通过条件在读取确认数据前确定：主平均BA≥0.60、按人bootstrap95%下限>0.50；相对同条件B1平均提升≥0.03，配对95%下限>0。仅一个主比较，不沿用上一轮两个候选的97.5%区间。没有因样本小而取消配对条件。部署权重预先指定种子42，另要求该权重平均BA≥0.60且95%下限>0.50；不得根据确认结果改用43或44。两个关口均通过才做隔离ARM导出／数值／耗时验证，不代表可以直接控制执行器。

若失败，保存所有成绩并停止该候选，不再把这12人称为未见确认集、不在它们上调参。本轮统计区间仅针对该12人条件；不能证明Cyton设备迁移、连续滤波迁移、静息拒绝或灵巧手安全。旧佩戴记录没有MI标签，后续只能检查计算与信号流程，不能用来报告左右手准确率。

复现入口（输出目录既有锁定和结果均禁止覆盖）：

```powershell
cd D:\ican\codex_project\eeg_apps_z15
.\.venv-mi\Scripts\python.exe -X utf8 -m unittest test_mi_confirmation -v
.\.venv-mi\Scripts\python.exe -X utf8 mi_confirmation.py lock
.\.venv-mi\Scripts\python.exe -X utf8 mi_confirmation.py train
.\.venv-mi\Scripts\python.exe -X utf8 mi_confirmation.py download
.\.venv-mi\Scripts\python.exe -X utf8 mi_confirmation.py extract
.\.venv-mi\Scripts\python.exe -X utf8 mi_confirmation.py evaluate
.\.venv-mi\Scripts\python.exe -X utf8 mi_confirmation.py verify
```
