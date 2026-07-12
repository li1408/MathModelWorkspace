# 队友上手指南 👋

欢迎加入这个数学建模工作流。这个文件的目标很简单：让队友从克隆仓库开始，一步一步把 VS Code、Python、LaTeX 和提交检查跑通。🙂

## 你会用到什么 🧩

请先确认电脑上已经有这些工具：

- Git：用于克隆和同步仓库。
- VS Code：作为主要工作台。
- Python：用于数据处理、建模、画图和检查脚本。
- MiKTeX：用于 LaTeX 编译。
- Strawberry Perl：用于运行 `latexmk`。
- VS Code 扩展：LaTeX Workshop、Python、Pylance、Jupyter、GitLens、Markdown All in One、Error Lens、Code Spell Checker。

建议把项目放在 E 盘或其他非 C 盘位置。不要把大数据、虚拟环境和缓存放到 C 盘。💾

## 第一步：克隆仓库 📦

推荐使用带 submodule 的克隆命令：

```powershell
cd E:\AI
git clone --recurse-submodules https://github.com/li1408/MathModelWorkspace.git
```

如果你已经普通克隆了仓库，再运行：

```powershell
cd E:\AI\MathModelWorkspace
git submodule update --init --recursive
```

`resources/MathModelHub/` 是参考资料库，不是正式写论文的位置。

## 第二步：打开正式项目 🧭

建议 VS Code 直接打开正式项目目录：

```powershell
code E:\AI\MathModelWorkspace\competitions\CUMCM2026
```

后续所有比赛相关工作都优先在这个目录里完成。

## 第三步：创建 Python 环境 🐍

进入项目目录：

```powershell
cd E:\AI\MathModelWorkspace\competitions\CUMCM2026
```

创建虚拟环境：

```powershell
python -m venv .venv
```

安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

检查 Python 流水线：

```powershell
.\.venv\Scripts\python.exe 04_code\run_all.py --dry-run
```

如果能看到数据检查、数据清洗、模型、验证、画图、导出结果等阶段列表，说明 Python 工作流已经可用。✅

## 第四步：配置 LaTeX 环境 📄

本项目默认使用：

- `ctexart`
- XeLaTeX
- BibTeX
- `gbt7714-numerical`
- `latexmk -xelatex`

运行本地路径初始化脚本：

```powershell
.\scripts\setup_local_paths.ps1
```

检查 LaTeX 环境：

```powershell
.\scripts\check_latex_env.ps1
```

看到 Perl、latexmk、ctexart、gbt7714 都是 OK，才说明编译环境准备好了。

## 第五步：编译论文 🛠️

进入论文目录：

```powershell
cd E:\AI\MathModelWorkspace\competitions\CUMCM2026\07_paper
```

正式编译：

```powershell
..\.local\bin\latexmk.cmd -xelatex -outdir=build main.tex
```

生成的 PDF 在：

```text
E:\AI\MathModelWorkspace\competitions\CUMCM2026\07_paper\build\main.pdf
```

`build/` 目录不会上传 GitHub，这是正常的。

## 第六步：跑提交检查 🔍

回到项目根目录：

```powershell
cd E:\AI\MathModelWorkspace\competitions\CUMCM2026
```

草稿检查：

```powershell
.\.venv\Scripts\python.exe 10_submission_check\check_submission.py --root . --mode draft
```

说明：

- draft 模式允许论文里有 `\placeholder{}`，会报 WARNING。
- final 模式不允许占位符，会报 ERROR。
- 自动检查不能代替人工合规复核。最终提交前必须至少两个人交叉检查。👀

## 放文件的位置 🗂️

如果你不确定文件属于哪一类，先全部放到 `00_inbox/`，然后告诉队长或 Codex：

```text
题目和附件已经放到 00_inbox，请整理到正式目录。
```

| 内容 | 放到哪里 |
| --- | --- |
| 不会分类的题目和附件 | `00_inbox/` |
| 题目文件 | `01_problem/` |
| 官方通知和规则 | `00_official/` |
| 原始数据 | `02_raw_data/` |
| 清洗后数据 | `03_processed_data/final/` |
| 中间数据 | `03_processed_data/interim/` |
| Python 代码 | `04_code/` |
| 模型输出 | `05_model_results/` |
| 论文图 | `06_paper_assets/figures/` |
| 论文表 | `06_paper_assets/tables/` |
| LaTeX 论文 | `07_paper/` |
| AI 使用记录 | `09_ai_logs/` |
| 最终提交文件 | `11_final_submission/` |

## 不要上传这些东西 🚫

- `.venv/`
- `.local/`
- `00_inbox/` 里的真实题目、附件和大文件
- `07_paper/build/`
- LaTeX 辅助文件，例如 `.aux`、`.log`、`.xdv`
- 本地敏感词文件：`10_submission_check/sensitive_terms.local.yml`
- 大体积原始数据、临时数据、缓存文件
- 未确认可公开的比赛材料

如果有大文件，只记录在 `02_raw_data/data_manifest.csv`，并保存本地或私有备份。

## 日常协作方式 🌱

先同步：

```powershell
git pull
git submodule update --init --recursive
```

查看状态：

```powershell
git status
```

建议分支：

- `main`：稳定版本。
- `dev`：日常整合版本。
- `feature/*`：新模型、新章节、新分析。
- `fix/*`：修复错误。

提交前先确认没有误加入大文件、敏感文件和编译产物。

## 常见问题 🧯

### LaTeX Workshop 弹出宏包安装，但点了没反应

先不要反复点弹窗。进入项目目录运行：

```powershell
.\scripts\check_latex_env.ps1
```

如果缺少包，优先修复 MiKTeX 环境，不要把问题误认为 LaTeX 源码错误。

### GitHub 上看不到 MathModelHub 具体文件

这是 submodule。运行：

```powershell
git submodule update --init --recursive
```

### final 检查为什么失败

模板阶段失败是正常的。final 模式必须等到：

- 占位符全部清除；
- 敏感词本地配置完成；
- 最终 PDF 放入 `11_final_submission/`；
- SHA256 校验值生成并验证；
- 学校和赛区附加规则确认。

## 最后提醒 🌟

这个仓库不是只为了“能编译”，而是为了让比赛过程更稳定：数据不乱、代码可追溯、论文能复核、最终提交有检查。按目录放文件，按命令做验证，队伍协作会轻松很多。🙂
