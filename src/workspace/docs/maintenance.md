# 长期维护方式

## 本机状态

正式目录 `D:/fpga/z15_multimodal` 已初始化本地 Git main 与 Trellis 0.6.7，身份 sds。最初执行用户原命令 `trellis init -u sds --claude --codex --skip-existing`，因状态栏询问遇到非交互 stdin 而失败；随后增加 `--yes` 使用默认设置成功。保留安装日志中这个差异，不声称原命令一次成功。

Claude Code 配置在 `.claude/`，Codex 配置在 `.codex/`，共享开发技能在 `.agents/skills/`。Trellis 默认生成的 Web 前后端规范已标明适用边界，新增硬件与项目规范。Codex 使用默认 inline 模式。

自动 hook 注入尚未验证。初始化输出提示 Codex 全局 hooks 设置与一次性 hook 审批可能需要用户在客户端完成；本轮没有改全局设置，也不将初始化成功写成 hook 已生效。即使没有自动注入，也可读取 AGENTS.md 并使用本地脚本维护任务和日志。

## 后续每次工作

1. 从 README、docs/status.md 和相关任务开始，读取 `.trellis/spec/project/index.md` 及工作层规范。
2. 查看任务：`python .trellis/scripts/task.py list`；查看上下文：`python .trellis/scripts/get_context.py`。
3. 新任务使用 `task.py create`；记录需求 prd.md，复杂任务补 design.md 和 implement.md。先解决对应阶段的未决事实，再开始代码和上板工作。
4. 保存真实验证证据，更新状态、决策和规范；用 `add_session.py` 写维护日志。
5. Git 提交包含本次实际变更；维护任务状态与源码进度一致。当前未设置远端、未发布。

`task.py start` 依赖当前会话身份；如果客户端未注入身份，遵循脚本提示配置，不伪造其他任务的 ID。规划中的基线任务没有自动开始硬件实现。

## 维护资料与成果

原始 PDF、镜像、安装包和旧 ZIP 留在原位置，引用与 hash 记入 docs/source_inventory.csv。本机路径快照在 Git 忽略的 local/。正式源码只保留一份，由构建脚本引用；不要把 Vivado 缓存当作交付。

后续迁移现有空工程时，在 build/ 中建立相对路径 Tcl 重建入口，先验证新工程，再决定旧工程用途。本轮不复制 .cache、.hw、.sim 或安装目录。

Trellis 的 `.agents/skills/` 服务开发维护；比赛的 `skill/` 是经实际失败与验证提炼出来的可复用成果。两者不能互相冒充。会话摘要只作索引，赛方要求的提示词、回答和自我纠错原始记录另保存在 report/ai_collaboration/。

## 事实与规划的写法

状态采用“规划、实现中、仿真通过、上板通过、整机验收”这样的可区分记录。完成声明必须附源码版本、配置和证据；不把文件数量、空脚本、模型文件名或目录结构写成完成度。

当前 v2 源码、电脑工具、仿真和 routed bitstream 已完成；实物性能仍待验证。维护入口为 build/screen、tools/screen_*、report/screen，以及 .trellis/spec/hardware/screen-contract.md。
