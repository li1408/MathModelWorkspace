# CUMCM2026 数学建模工作区

本目录用于 2026 全国大学生数学建模竞赛的本地实战。核心链路为：MathModelHub 提供参考，VS Code 组织项目，MiKTeX/XeLaTeX 编译论文，LaTeX Workshop 预览与定位错误，Python/Jupyter 计算和绘图，Codex 辅助生成、修改、检查与修复，Git/GitHub 负责私有版本管理。

## 目录说明

| 目录 | 用途 |
| --- | --- |
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

- MiKTeX Portable：`E:\Tools\MiKTeXPortable-CUMCM`
- Strawberry Perl：`E:\Tools\Strawberry`
- Python 虚拟环境：项目根目录 `.venv/`
- 临时文件和工具缓存：项目根目录 `.local/`

`C:\Strawberry` 和用户 MiKTeX 路径若存在，仅作为指向 E 盘的 junction；项目包装器直接调用 E 盘真实路径。

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

原始数据只放入 `02_raw_data/`，不得原地覆盖。大文件必须登记 `data_manifest.csv`、记录 SHA256，并至少保留一份本地或私有备份。

## 提交检查

```powershell
.\.venv\Scripts\python.exe 10_submission_check\check_submission.py --root . --mode draft
.\.venv\Scripts\python.exe 10_submission_check\check_submission.py --root . --mode final
```

draft 允许占位符并报告 WARNING；final 中任何占位符、本地敏感词配置缺失、最终文件缺失或 SHA256 不一致都会报告 ERROR 并返回退出码 1。

实际身份敏感词必须从 `sensitive_terms.example.yml` 复制到 `sensitive_terms.local.yml` 后填写；local 文件已被 Git 忽略。自动检查不能替代最终双人交叉合规复核。
