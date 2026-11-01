"""Write the deployment handoff from stored audit artifacts."""
import json
import time
import urllib.request

from validate_ssvep_shadow import OUT


def read(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))


def main():
    audit, replay, deploy = read('audit.json'), read('replay_report.json'), read('deployment.json')
    manifest = read('manifest.json')
    paced = audit['paced_check']
    with urllib.request.urlopen('http://192.168.2.99:9102/api/ssvep-shadow',timeout=5) as response:
        observed = json.load(response)
    (OUT/'live_postcheck.json').write_text(json.dumps({'observed_pc_time':time.time(), **observed},indent=2),encoding='utf-8')
    initial = read('initial_candidate_profile.json')['runs']
    current = read('candidate_profile.json')['runs']
    lines = [
        '# SSVEP O1/O2 只读旁路接入与部署记录', '',
        '## 已实现', '',
        '固定八通道 F3,F4,C3,C4,T7,T8,O1,O2 不变；旁路仅使用 O1/O2 原始微伏值，'
        '在原有中心化、情绪/疲劳滤波和 PL 量化之前取得数据。50Hz/Q30 陷波、6–45Hz 因果带通、'
        '500点/2秒 CCA窗、50点/200ms步长、10点批次沿用已验证候选；均在 ARM 运行，无 PL 加速。', '',
        '- 消费真实包计数器（含255→0回绕）、异常字节和读取时刻。跳号、重复、倒序、超过250ms的读取间隔清空候选、滤波与缓存。',
        '- 无包超过500ms、服务结束、非有限值或ADC接近满量程时清空旧候选；重连需重新积累660点（2.64秒）。',
        '- 与情绪/疲劳模型并行的“只读”指不影响其输入/决策，也不发送控制；旁路仍消耗ARM时间并写自己的状态文件。',
        '- 网页区分未收到及时数据、热身、信号不合格和观察候选；输入年龄超过750ms时隐藏频率。历史回放使用独立文件，绝不充当实时输入。', '',
        '## 工程质量规则及限制', '',
        '复用 `cyton_sqi.channel_sqi` 的描述量，不修改生产SQI代码。O1/O2原始与滤波描述量合并为一次计算；其余六通道不影响此候选。'
        '无个人基线/校准，不能复用情绪模型的六通道门槛来宣称SSVEP可信。', '',
        '- 拒绝：原始/滤波平线比例≥0.95；滤波后去中位数绝对幅值p99>100µV；所选通道非有限值、ADC接近满量程、数值秩不足。',
        '- 警告：原始工频比例>0.20、原始p99>100µV、原始突变比>40或残余工频比例>0.20。软警告不代表修复成功。',
        '- 100µV是p99工程门限，不等同于PL逐点±100µV门控。本旁路不经过±327.67µV传输量化，未冒用其裁剪规则。',
        '- CCA总会在预设8/10/12/14Hz中选相对最高分。正常α节律也可能产生候选；没有刺激同步/无目标标签时，不能解释为用户注视或控制意图。`control_enabled=false`不可被事件覆盖。', '',
        '## 验证', '',
        f"历史Cyton输入 {replay['samples']} 点 / {replay['input_seconds']:.3f}秒；SHA256 `{replay['input_sha256']}`。"
        '位置是用户历史声明，文件头仅有CH编号；无SSVEP任务标签，不报告准确率。', '',
        f"- 共 {replay['events']} 个重叠滚动窗，状态分布 `{replay['states']}`；原始序号异常 {replay['sequence_gaps']} 次。此计数不是独立试次样本数。",
        f"- PC/ARM门控状态、频率与窗口端点核对通过；CCA最大误差 {audit['recorded_bridge_pc_arm']['maximum_score_error']:.3g}。",
        f"- 完整主循环的情绪/疲劳逐窗口结果接入前后一致：`{audit['parity']}`。原始与合成输入分开保存，不以合成波形证明佩戴准确率。",
        '- 板端首轮30项回归测试通过，最终旁路11项测试通过；本机包含情绪/疲劳模块的32项测试通过，另13项SSVEP核心测试通过。', '',
    ]
    for before, row, timing in zip(initial,current,audit['timing']):
        lines.append(f"- {row['case']}（{row['input_seconds']:.3f}秒输入）：原主循环 {timing['baseline_wall_s']:.2f}秒；"
                     f"初版旁路 {before['wall_s']:.2f}秒；最终修正版 {row['wall_s']:.2f}秒。"
                     f"最终模拟积压 {row['simulated_queue_delay_final_ms']:.1f}ms，最大 {row['simulated_queue_delay_max_ms']:.1f}ms。")
    lines += ['', audit['initial_check'], '',
              '上述加速回放不是实际USB队列测量。结束时恰逢主窗口计算会留下终端延后；保留第一次未通过200ms检查的文件，'
              '不删除失败结果。第二版仅合并SQI，180秒合成输入仍用了145.49秒，未达到20%计算余量门槛。'
              '热点检查随后发现候选更新之间被误写为热身，重复发布状态；最终版修复此错误、补充保持状态测试，并将逐包的两元素NumPy归约改为标量检查。'
              '未改变质量门限或模型参数。当前工程准入条件：', '',
              audit['acceptance'], '',
              f"90秒真实读取器/管道定速回放：消费 {paced['report']['packets_consumed']}/{paced['report']['packets_expected']} 包，"
              f"观察到的快照输入年龄p95={paced['input_age_p95_ms']:.1f}ms，最大={paced['input_age_max_ms']:.1f}ms；"
              f"监测错误 `{paced['report']['monitor_errors']}`。仍非USB无线链路、浏览器绘图/网络端到端或硬实时保证。", '',
              '## 部署与恢复', '',
              f"部署状态：`{deploy['phase']}`；备份目录：`{deploy['backup']}`。",
              f"原情绪/疲劳/SEED模型与其处理模块哈希不变：`{deploy['protected_unchanged']}`；bitstream/hwh前后哈希一致。",
              '仅替换 `cyton_guardianloop.py`、`guardianloop_web.py`，添加SSVEP依赖及冻结配置。重启了两项服务以加载代码，未重启板卡、未加载新的Overlay。', '',
              f"部署后另一次实时API观察：state=`{observed['live']['state']}`，stale=`{observed['stale']}`，"
              f"包数=`{observed['live'].get('packets_seen')}`，控制启用=`{observed['live']['control_enabled']}`。"
              '浏览器已核对新增卡片、实时来源与历史回放标识；未触发任何佩戴记录或控制操作。', '',
              '恢复命令（在Z15 Linux执行）：', '', '```sh',
              f"cp -p {deploy['backup']}/cyton_guardianloop.py {deploy['backup']}/guardianloop_web.py /home/xilinx/jupyter_notebooks/guardianloop_pynq/",
              'sudo systemctl restart guardianloop-cyton.service guardianloop-web.service', '```', '',
              '新增模块可保留，旧入口不会调用；不需要删除数据或重新刷SD卡。', '',
              '## 状态与复现材料', '',
              '- 实时状态：`/tmp/guardianloop-ssvep-shadow.json`；历史回放：`/tmp/guardianloop-ssvep-replay.json`。',
              '- API：`/api/ssvep-shadow`；有线网页 http://192.168.2.99:9102/；板卡热点网页 http://192.168.50.1:9102/。',
              '- `manifest.json`：生产原文件与候选SHA256；`initial_*`、`combined_*`：前两次实现、源文件与未通过的检查证据；`hotspots.txt`：短段开销分析；`audit.json`：逐窗一致性、性能与准入条件。',
              '- `replay_report.json`、`replay_events.json`：旧记录门控结果；`*_profile.json`：全主循环耗时；`paced_report.json`、`paced_monitor.jsonl`：90秒定速回放。',
              '- `deployment.json`：恢复路径、安装哈希、服务状态及部署时HTTP响应。',
              f"- 隔离工作目录：`{manifest['stage']}`。", '',
              '运行脚本为 `validate_ssvep_shadow.py`（首次隔离验证）、`--optimized-check`（保留初始证据后的重复计算优化验证）、'
              '`--final-check`（逐包开销与假热身修正）、`--paced-check`（90秒完整链路）、`deploy_ssvep_shadow.py`（通过门槛才部署）及 `report_ssvep_shadow.py`。'
              '现有输出有防覆盖保护；不要对已部署记录盲目重跑。', '',
              '## 下一步边界', '',
              '本步完成只读观察接入；无需重新佩戴。若要升级成实际脑控，需要先验证刺激屏时序、无注视/非目标拒绝及误触发率，'
              '不能凭本次回放或网页出现某个Hz就启用控制。', '']
    (OUT/'RESULTS.md').write_text('\n'.join(lines),encoding='utf-8')


if __name__=='__main__':
    main()
