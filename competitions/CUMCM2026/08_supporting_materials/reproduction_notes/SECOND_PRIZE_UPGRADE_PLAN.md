# Implementation Plan: 2025 CUMCM D 题二等奖质量升级

## Architecture Decisions

- 先修正可被小网络反例证明的问题，再处理真实附件，避免在错误模型上润色论文。
- 保持现有 `run_all.py` 单入口；新增验证指标，不新增网络依赖。
- 结果表以官方模板为格式源，计算值以 CSV/内存结果为数据源。
- 论文通过由代码生成的汇总表或明确的结果文件回填，避免手工复制时失配。

## Phase 1: 模型合同与反例测试

### Task 1: 固化水流不变量

- Acceptance：小网络覆盖单边传播、等分流、合流、延迟双源和原始巷道拆边；测试能暴露当前实现的错误。
- Verify：新增测试在旧实现上失败，修复后通过。
- Files：`04_code/tests/test_water_flow_invariants.py`，必要时 `04_code/water_flow.py`、`04_code/graph_utils.py`。
- Dependencies：无。

### Task 2: 固化动态逃生不变量

- Acceptance：覆盖穿越期间来水、顺逆流速度、0.3 m 阈值和通知时刻状态。
- Verify：新增测试在旧实现上失败，修复后通过。
- Files：`04_code/tests/test_escape_routing_invariants.py`，必要时 `04_code/escape_routing.py`。
- Dependencies：Task 1。

### Checkpoint 1

- 全部模型单元测试通过；每个关键假设都有公式、单位和测试证据。

## Phase 2: 真实数据与结果闭环

### Task 3: 修正问题四在途状态

- Acceptance：第二突水发生至调整通知的一分钟内，矿工位置和可通行性受双源水流约束。
- Verify：场景测试和真实矿工路径连续性检查通过。
- Files：`04_code/d_workflow.py`、对应测试、结果汇总。
- Dependencies：Task 2。

### Task 4: 保留官方结果模板并扩展验证

- Acceptance：八个工作簿保持模板表头/样式；无虚拟巷道编号泄漏；两位小数、形状和路径连续性正确。
- Verify：模板比较测试、工作簿渲染抽查和 `validate_generated_results()` 通过。
- Files：`04_code/output_writer.py`、`04_code/d_workflow.py`、输出测试。
- Dependencies：Task 1–3。

### Task 5: 生成有区分度的实验和图表

- Acceptance：给出关键到达/充满统计、六名矿工 Q2/Q4 路径结果、流量和阈值灵敏度、至少一个人工小网络对照。
- Verify：CSV 指标非空、图表存在且正文可引用。
- Files：`04_code/d_workflow.py`、`08_sensitivity_analysis.py`、`09_generate_figures.py`、验证测试。
- Dependencies：Task 4。

### Checkpoint 2

- 完整流水线成功；八个结果表和图表通过自动与人工抽样验证。

## Phase 3: 论文与比较模块

### Task 6: 重写论文方法与结果章节

- Acceptance：摘要、逐问结果、验证、灵敏度、评价全部有真实数值和交叉引用；模型叙述与代码一致。
- Verify：无占位符；数字追溯检查通过；XeLaTeX 编译通过。
- Files：每次最多修改 3–5 个 `07_paper/sections/*.tex` 文件。
- Dependencies：Checkpoint 2。

### Task 7: 完成图表、参考文献和附录

- Acceptance：正文引用实际图表；文献真实且正文引用；支撑材料与 AI 使用说明可追溯。
- Verify：引用检查、PDF 渲染和人工视觉检查通过。
- Files：`07_paper/main.tex`、`references.bib`、附录及必要样式文件。
- Dependencies：Task 6。

### Task 8: 建立获奖论文比较模块

- Acceptance：建立输入说明、评分量表和当前论文自评；拿到获奖论文后可重复生成差距报告。
- Verify：无原文时明确标记未比较，不把自评伪装成获奖论文事实。
- Files：`09_award_compare/README.md`、量表和报告模板。
- Dependencies：可与 Task 6–7 并行。

## Phase 4: 最终质量门禁

### Task 9: 独立审查与提交预检

- Acceptance：模型与代码接受独立反例审查；Critical/Important 问题清零；draft 无 ERROR。
- Verify：全测试、完整流水线、XeLaTeX、PDF 视觉检查、draft/final 检查均记录结果。
- Dependencies：Task 1–8。

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 题面对“巷道充满”的水力过程未给出完整方程 | 高 | 明确近似、用守恒和小网络验证，并把复杂模型作为备选而非暗中假设 |
| 双源合流使事件流量随时间变化 | 高 | 使用可重放事件/分段流量状态，测试延迟源和汇合节点 |
| 当前 Excel 写出破坏官方模板 | 高 | 以模板为格式源，只填计算区域并做渲染对比 |
| 论文结果与重算结果漂移 | 高 | 结果先冻结，再自动生成汇总并逐项核对 |
| 获奖论文原文缺失 | 中 | 先完成自评框架，等待用户提供输入，不阻塞主线 |
