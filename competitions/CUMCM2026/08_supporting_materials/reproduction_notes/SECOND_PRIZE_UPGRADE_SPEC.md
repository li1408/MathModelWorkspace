# Spec: 2025 CUMCM D 题二等奖质量升级

## Objective

把当前“能够运行和编译的测试稿”升级为一套可复现、可解释、可核验的完整竞赛成果。目标是达到国赛二等奖常见的质量门槛，而不是承诺奖项：题意解释与代码一致，核心模型满足明确的不变量，八个结果工作簿符合官方模板，论文中的每个数值、图表和结论都可追溯到程序输出。

## Tech Stack

- Python 3.10：图模型、事件仿真、动态路径、验证、灵敏度和绘图。
- pandas / NumPy / SciPy / Matplotlib：数据处理与实验。
- 现有 Excel 模板：保留官方 sheet、表头、样式和两位小数要求。
- XeLaTeX + BibTeX + gbt7714：中文论文编译与真实文献管理。

## Commands

```powershell
# 模型测试
.\.venv\Scripts\python.exe -m unittest discover -s 04_code\tests -p "test_*.py" -v

# 完整流水线
.\.venv\Scripts\python.exe 04_code\run_all.py

# LaTeX 环境与编译
.\scripts\check_latex_env.ps1
cd 07_paper
..\.local\bin\latexmk.cmd -xelatex -outdir=build main.tex

# 提交检查
.\.venv\Scripts\python.exe 10_submission_check\check_submission.py --root . --mode draft
.\.venv\Scripts\python.exe 10_submission_check\check_submission.py --root . --mode final
```

## Project Structure

- `01_problem/`：题面与问题拆解，作为模型合同。
- `02_raw_data/`：只读附件和官方结果模板。
- `04_code/`：模型与自动化测试。
- `05_model_results/`：八个结果表、指标、验证与灵敏度证据。
- `06_paper_assets/`：论文实际引用的图表。
- `07_paper/`：完整论文源码和编译产物。
- `08_supporting_materials/`：复现说明、代码快照和结果副本。
- `09_award_compare/`：获奖论文输入、比较量表和差距报告。
- `10_submission_check/`：自动门禁与人工清单。

## Code Style

核心逻辑使用带单位的命名、纯函数优先，并把物理不变量写成可执行测试。例如：

```python
def travel_time_min(length_m: float, speed_m_per_min: float) -> float:
    if length_m < 0 or speed_m_per_min <= 0:
        raise ValueError("length and speed must be physically valid")
    return length_m / speed_m_per_min
```

禁止在论文和代码中用无法解释的“经验常数”替代题面参数；必要近似必须同时说明适用范围和验证方法。

## Testing Strategy

- 单元测试：投影拆边、分流、质量守恒、合流、到达/充满时刻、分段通行时间。
- 场景测试：单源、延迟双源、水平环路、同一巷道多个虚拟点、第二突水后的在途矿工。
- 输出测试：模板 sheet、表头、样式、行列、两位小数、节点/巷道编号和路径连续性。
- 集成测试：`run_all.py` 生成八个结果工作簿、指标、图表和支撑材料。
- 论文门禁：无占位符、无未定义引用、正文数字与 CSV/Excel 自动核对、PDF 视觉检查通过。

## Boundaries

### Always

- 保留原始数据和模板不变；所有结果由代码生成。
- 先写失败测试，再修改模型逻辑。
- 论文只使用已运行并人工抽样复核的数值。
- 每个非平凡模型决定都接受独立反例审查。

### Ask First

- 题面无法唯一决定的水力学解释需要改变主模型时。
- 需要用户提供此前的获奖论文 PDF 或真实身份敏感词时。
- 需要删除现有结果、历史日志或用户已有代码时。

### Never

- 编造参考文献、实验结果、官方规则或获奖结论。
- 修改 `02_raw_data/` 原始附件。
- 把本机路径、身份信息或未复核 AI 文本带入最终提交物。

## Success Criteria

1. 题面参数、单位和四问时间线均有自动测试。
2. 水流模型对每个事件可解释，并对分流/合流给出质量守恒证据。
3. 动态路径计算处理水流在穿越巷道期间到达、顺逆流速度变化和 0.3 m 阈值。
4. 问题四使用第二突水发生后的真实在途状态，而非无条件沿旧路线线性插值。
5. 八个结果工作簿保持官方模板结构与样式，数值为两位小数且通过完整性检查。
6. 验证至少包括结构检查、守恒检查、人工可算小网络对照和参数灵敏度。
7. 论文包含定量摘要、逐问结果、有效图表、局限性、真实引用和复现说明；无占位符。
8. XeLaTeX 干净编译，PDF 无明显排版缺陷，draft 提交检查无 ERROR。
9. final 模式只允许因真实身份敏感词或最终冻结动作尚未由队伍完成而保留的明确人工步骤。

## Open Questions

- 先按题面可直接支持的“事件驱动等分流模型”做严谨闭环；若独立审查证明该模型不足以解释充满过程，再向用户确认是否采用更复杂的蓄水/水力学主模型。
- 获奖论文比较需要用户把原 PDF 放入 `09_award_compare/input/`；缺少原文不阻塞模型和论文主体升级。
