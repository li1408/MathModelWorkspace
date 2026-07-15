# CUMCM2026 数学建模工作区

本目录用于 2026 全国大学生数学建模竞赛的本地实战。核心链路为：MathModelHub 提供参考，VS Code 组织项目，MiKTeX/XeLaTeX 编译论文，LaTeX Workshop 预览与定位错误，Python/Jupyter 计算和绘图，Codex 辅助生成、修改、检查与修复，Git/GitHub 负责私有版本管理。

## 目录说明

| 目录 | 用途 |
| --- | --- |
| `00_inbox/` | 队友临时投递题目 PDF、附件文件夹和说明文件；由 Codex 再整理到正式目录 |
| `00_official/` | 全国、赛区和学校正式通知与格式规则 |
| `01_problem/` | 赛题原文、附件说明、问题拆解和选题记录 |
| `02_raw_data/` | 只读原始数据、数据清单和校验值 |
| `03_processed_data/` | 清洗数据和中间数据 |
| `04_code/` | Python 数据处理、建模、验证、敏感性分析和导出代码 |
| `05_model_results/` | 模型输出、指标、运行记录和实验结果 |
| `06_paper_assets/` | 论文实际引用的图、表和 draw.io 源文件 |
| `07_paper/` | `ctexart + XeLaTeX + BibTeX` 论文源码与 build 输出 |
| `08_supporting_materials/` | 可复现说明、代码快照和支撑材料 |
| `09_ai_logs/` | AI 实质性使用记录及提示词/回复原文 |
| `10_submission_check/` | 自动提交检查、规则、敏感词和测试 |
| `11_final_submission/` | 冻结后的最终提交文件及 SHA256 |

## 首次使用

在项目根目录运行：

```powershell
.\scripts\setup_local_paths.ps1
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\check_latex_env.ps1
```

当前项目使用：

- MiKTeX：真实目录记录在 `.local/miktex-bin.path`
- Perl：真实目录记录在 `.local/perl-bin.path`
- Python 虚拟环境：项目根目录 `.venv/`
- 临时文件和工具缓存：项目根目录 `.local/`

项目包装器直接读取上述路径文件，论文和支撑材料中不写入机器绝对路径。

## 论文编译

正式默认编译：

```powershell
cd 07_paper
..\.local\bin\latexmk.cmd -xelatex -outdir=build main.tex
```

LaTeX Workshop 默认使用同一配方，所有辅助文件进入 `07_paper/build/`。自动宏包安装已禁用，缺包会立即返回明确错误，避免 MiKTeX 图形界面无响应。

当前没有真实参考文献时，`main.tex` 中 `\usereferencesfalse` 保持关闭。加入真实 BibTeX 条目并在正文使用 `\cite{}` 后，再改为 `\usereferencestrue`。

## Python 与 Jupyter

VS Code 默认解释器为 `.venv/Scripts/python.exe`。pip、Python 临时文件、matplotlib 和 Jupyter 缓存均通过 `.env.workspace` 与 VS Code 设置写入 `.local/`，不会把项目大包或缓存写入 C 盘。

检查代码调度：

```powershell
.\.venv\Scripts\python.exe 04_code\run_all.py --dry-run
```

运行模型不变量与输出合同测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s 04_code\tests -p 'test_*.py' -v
```

测试使用 Python 标准库 `unittest`，无需额外安装 `pytest`。完整实跑使用：

```powershell
.\.venv\Scripts\python.exe 04_code\run_all.py
```

无参数命令保持原有 Q1--Q4 基线流程，不会自动运行耗时的替代模型、空间收敛或冷启动复现。需要检查模型可信度时使用：

```powershell
# 日常基线与论文输出
.\.venv\Scripts\python.exe 04_code\run_all.py --profile practice

# 替代模型、FIFO、收敛、比较审计和证据链
.\.venv\Scripts\python.exe 04_code\run_all.py --profile audit

# 增加冷启动、严格证据和提交门禁
$env:CUMCM_INPUT_ROOT = (Resolve-Path 02_raw_data)
.\.venv\Scripts\python.exe 04_code\run_all.py --profile final
```

每次显式 profile 运行都会生成唯一 `run_id`，结果隔离到 `05_model_results/runs/<run_id>/`，并保存运行清单、配置快照、输入校验值、环境信息和阶段报告。该目录可能包含大文件，默认不进入 Git，并始终保存在本项目所在的 E 盘。

阶段选择规则：`--stage <name>` 只运行一个阶段；`--from-stage <name>` 从指定阶段运行到 profile 末尾；`--stages a,b,c` 只运行显式列表。三者不能混用。可用 `--run-id <id>` 继续同一次隔离运行。

论文重要结论登记在 `07_paper/evidence/claims.csv`，证据链接登记在 `evidence_links.csv`。图表技术信息和人工复核状态登记在 `06_paper_assets/figure_manifest.csv`。脚本只核对文件、指标和校验值，不能替代人工判断模型与图表是否真正支持结论。

原始数据只放入 `02_raw_data/`，不得原地覆盖。大文件必须登记 `data_manifest.csv`、记录 SHA256，并至少保留一份本地或私有备份。

## 队友投递材料

队友如果不清楚题目和附件应该放哪里，可以先全部放到：

```text
00_inbox/
```

放好后告诉 Codex：

```text
题目和附件已经放到 00_inbox，请整理到正式目录。
```

Codex 会把官方规则、题目原文、原始数据和附件分别整理到 `00_official/`、`01_problem/`、`02_raw_data/`，并更新数据清单和 SHA256。`00_inbox/` 的真实文件默认不进入 Git。

## 提交检查

```powershell
.\.venv\Scripts\python.exe 10_submission_check\check_submission.py --root . --mode draft
.\.venv\Scripts\python.exe 10_submission_check\check_submission.py --root . --mode final
```

draft 允许占位符并报告 WARNING；final 中任何占位符、本地敏感词配置缺失、最终文件缺失或 SHA256 不一致都会报告 ERROR 并返回退出码 1。

实际身份敏感词必须从 `sensitive_terms.example.yml` 复制到 `sensitive_terms.local.yml` 后填写；local 文件已被 Git 忽略。自动检查不能替代最终双人交叉合规复核。
