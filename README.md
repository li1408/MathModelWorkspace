# MathModelWorkspace

这是一个面向数学建模竞赛的可复现工作区。核心环境为 MiKTeX、VS Code、LaTeX Workshop、Codex、Python、Git 和 GitHub。

## 工作区结构

- `resources/MathModelHub/`：MathModelHub 参考库，只用于查阅算法、模板、Notebook 和工作流资料。
- `competitions/CUMCM2026/`：当前正式工作项目，用于 2026 全国大学生数学建模竞赛训练和实战。
- `competitions/2026-practice-01/`：早期练习模板，保留作为结构参考。

## 基本原则

- `resources/` 只作为学习和参考来源，不在其中写正式比赛论文。
- 每个比赛或练习题单独放在 `competitions/<project-name>/`。
- CUMCM2026 原始数据放入 `02_raw_data/`，不直接修改。
- 清洗和中间结果写入 `03_processed_data/`、`05_model_results/` 或项目约定输出目录。
- 代码生成的图表和表格写入 `06_paper_assets/figures/`、`06_paper_assets/tables/`。
- 论文结论必须能追溯到 `04_code/` 中的脚本、Notebook、日志或模型输出。
- 不编造数据、实验结果、参考文献或图表。
- 大文件、虚拟环境、LaTeX 编译产物、本地敏感词配置和临时缓存不进入 Git。

## MathModelHub 引用方式

`resources/MathModelHub` 作为 Git submodule 记录到本仓库，指向：

```text
https://github.com/li1408/MathModelHub.git
```

克隆本仓库后，如需同步参考库，使用：

```powershell
git submodule update --init --recursive
```

同步后仍然把 `resources/MathModelHub` 当作参考库，不在其中写正式比赛论文。

## 当前项目

打开 VS Code 时建议直接打开：

```text
E:\AI\MathModelWorkspace\competitions\CUMCM2026
```

常用检查命令：

```powershell
.\scripts\check_latex_env.ps1
.\.venv\Scripts\python.exe 04_code\run_all.py --dry-run
.\.venv\Scripts\python.exe 10_submission_check\check_submission.py --root . --mode draft
```

论文正式编译命令：

```powershell
cd E:\AI\MathModelWorkspace\competitions\CUMCM2026\07_paper
..\.local\bin\latexmk.cmd -xelatex -outdir=build main.tex
```
