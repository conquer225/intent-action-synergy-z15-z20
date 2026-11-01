# 公开源码副本验证

本次在 Windows 11、Python 3.14.7 下，对公开副本恢复后的源码执行指定离线回归。全部结果标记 `board_executed: false`，不连接板卡或执行机构。

| 检查 | 数量 | 原始结果 |
| --- | ---: | --- |
| 指定原工程回归 | 12 | [工程日志](z20_regression.log) |
| 通用 PYNQ Skill | 14 | [Skill 日志](portable_skill.log) |
| 公开交付工具 | 7 | [交付工具日志](submission_tools.log) |
| 合计 | 33 | [汇总](offline_summary.json) |

检查器新增 Git 元数据与 `.gitignore`、`.gitattributes` 的公开 CLI 回归。该用例先复现原实现的拒绝行为，再确认修订后通过；其他未登记文件、损坏源码及超长路径继续拒绝。

4744 个公开源文件均保留原始字节，恢复前核对来源清单的大小和 SHA256。完整文件集合由仓库根 `sha256sums.txt` 固定；Git 元数据不在此集合中。最终远程推送、克隆及克隆后检查保存在本地发布记录，不回写当前提交以产生循环摘要。

复跑命令见[复现说明](../reproduction.md)。这些结果不替代 FPGA 重建、完整模型环境、上板测量、显示外观或真实机械动作验收。
