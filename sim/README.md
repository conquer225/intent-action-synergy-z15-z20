# 仿真与软件验证

`test_restore_workspace.py` 检查本次新增恢复命令的公开接口：恢复字节及原大小写、摘要损坏时不产生输出、越界路径拒绝、已有目录保留。它按先失败后实现运行。

`test_verify_package.py` 检查完整交付通过、摘要被改、未登记文件、非法文件名及超出 Windows ZIP 路径预算时拒绝。交付工具共 7 项测试，含多个故障子用例。

`run_checks.py` 对已还原工程执行选定的 12 项软件测试，并复跑本包 14 项技能测试和 7 项交付工具测试。软件故障注入、本机 socketpair 和合成位流均不登记为板卡测试。命令和当前结果保存在[检查记录](../report/verification/README.md)。

原 RTL/HLS 测试台在恢复后的 `sim/`、`integrations/vision_demo/tests`、`integrations/z20_compute/hardware/hls` 及各模块测试目录。历史 C 仿真、综合、RTL 数值核对和完整回归报告随源码保留；本次整理没有重新运行 Vivado/XSim/HLS。

`results/device_menu_20261030_checks.json` 是原 10/30 离线修订的历史结果，不能替代新候选的现场验收。重建固件时重新运行匹配版本的仿真、综合、实现、时序/CDC/DRC，再进行实板验证。

公开 Git 版本另验证 `.git/` 元数据与根 `.gitignore` 和 `.gitattributes`，确保克隆后仍可检查全部公开文件。该用例先在原检查器上失败，修订后通过。
