# Codex 工作规则

## 项目定位

本目录是正式数学建模工作项目。`../../resources/MathModelHub` 只作为参考库，不在其中写论文、不修改其文件，除非用户明确要求同步或整理参考资料。

## 修改规则

- 每次修改前先说明将要改哪些文件。
- 每次修改后总结改动、验证结果和下一步建议。
- 不编造数据、实验结果、图表、参考文献或结论。
- 原始数据只放在 `data/raw/`，不得覆盖或就地修改。
- 清洗后数据输出到 `data/processed/`，中间结果输出到 `data/interim/`。
- Python 生成的图像输出到 `figures/`，表格输出到 `tables/`。
- LaTeX 论文只能引用真实存在的图像和表格文件。
- 每个模型结论必须能追溯到 `code/` 中的脚本、Notebook 或 `logs/experiment_log.md`。
- 修改 LaTeX 后必须尽量编译验证；如果无法编译，要说明具体原因。

## 论文规则

- 中文论文默认使用 `ctexart` 和 XeLaTeX。
- 美赛英文论文需要用户明确要求后再切换到 `mcmthesis`。
- 参考文献通过 Zotero 导出到 `paper/references.bib`。
- 不要添加未实际阅读、未引用或来源不明的文献。
- draw.io 源文件可放在 `figures/`，导出的 PDF/PNG 才用于论文引用。

## 代码规则

- `code/preprocessing.py`：数据读取、清洗、字段标准化。
- `code/model.py`：模型建立和参数估计。
- `code/validation.py`：一致性、误差和稳健性检验。
- `code/sensitivity.py`：参数扰动和灵敏度分析。
- `code/visualization.py`：图像和表格输出。
- `code/utils.py`：路径、读写和通用工具。

## 交付前

提交前必须检查 `checklist/final_checklist.md`。
