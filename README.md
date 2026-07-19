# MathModelWorkspace 📐

面向 CUMCM 国赛和中文校赛的可复现数学建模工作区。Python 负责统一调度和计算，LaTeX/Word 负责论文，Codex 负责生成初稿、修改、检查与修复，所有正式结论必须经过人工门禁并能追溯到冻结运行。

## 这套工作流解决什么问题 🎯

- 题目、原始数据、处理后数据、代码、结果和论文各自归位。
- 原始数据只读并记录 SHA256，避免误改附件。
- 每个小问都有输入、输出、模型、验证和论文位置映射。
- 每个小问先完成故事板，再通过 H1/H3/H4 分别审查题目叙事、模型选择和验证设计。
- 模型运行生成唯一 `run_id`，不同实验不会互相覆盖。
- 重要结论链接到冻结结果、指标、图表和文件 hash。
- 摘要中的结果数字必须能追溯到冻结 evidence，不允许人工转抄后失去来源。
- H1-H8 由队员人工审批，Codex 和脚本不能自我批准。
- 每次等待 H1-H8 时自动生成按 `01` 到 `08` 排序的 AI+人工审核包，不再手工挑文件。
- 最终支撑材料按 allowlist 正向打包，默认排除身份与本机信息。

## 架构 🧩

```text
workflow_core/sdk <- plugins <- cases / competitions
        ^
competition_profiles、paper_templates 作为受验证的数据输入
```

| 目录 | 作用 |
| --- | --- |
| `workflow_core/` | 通用调度、Schema、审批、Run、证据、打包和复现 |
| `plugins/` | 题型能力声明和验证入口；第一轮只有 3 个 experimental 插件 |
| `cases/` | 具体案例桥接；矿井题作为首个回归案例 |
| `competition_profiles/` | 全国与学校规则，不包含模型逻辑 |
| `paper_templates/` | 模板注册、不可变原件和适配层 |
| `competitions/CUMCM2026/` | 当前练习项目及原有 Q1-Q4 流程 |
| `resources/MathModelHub/` | 只读学习资源，不在其中写正式论文 |

`workflow_core` 不导入具体插件、案例或比赛代码。插件和案例均通过受信任注册表、文件协议和独立 Python 子进程执行。

## 安装 🚀

建议把仓库、虚拟环境、临时目录和大数据都放在 E 盘或其他非 C 盘位置。

```powershell
cd E:\AI
git clone --recurse-submodules https://github.com/li1408/MathModelWorkspace.git
cd E:\AI\MathModelWorkspace

python -m venv competitions\CUMCM2026\.venv
.\competitions\CUMCM2026\.venv\Scripts\python.exe -m pip install -r competitions\CUMCM2026\requirements.txt
.\competitions\CUMCM2026\.venv\Scripts\python.exe -m pip install -e .
```

复制本地资产映射示例。真实路径文件被 Git 忽略：

```powershell
Copy-Item competitions\CUMCM2026\config\local\assets.local.example.yml `
  competitions\CUMCM2026\config\local\assets.local.yml
```

当前示例使用项目相对路径，一般不需要修改。队友必须在自己的电脑上准备相同附件并通过 SHA256 校验。

## 两条运行路径 ▶️

### 1. 原有矿井题基线流程

兼容入口完全保留，无参数行为不变：

```powershell
cd E:\AI\MathModelWorkspace\competitions\CUMCM2026
.\.venv\Scripts\python.exe 04_code\run_all.py --dry-run
.\.venv\Scripts\python.exe 04_code\run_all.py
```

### 2. 通用人工门禁流程

在仓库根目录运行：

```powershell
cd E:\AI\MathModelWorkspace
.\competitions\CUMCM2026\.venv\Scripts\python.exe -m workflow_core.cli.run_all `
  --project competitions/CUMCM2026 --profile practice --dry-run

.\competitions\CUMCM2026\.venv\Scripts\python.exe -m workflow_core.cli.run_all `
  --project competitions/CUMCM2026 --profile practice
```

实际运行会在 H1 暂停并返回退出码 `3`。队员检查审批请求后，手动登记审批：

同时会生成：

```text
competitions/<project>/09_review_packages/<run_id>/
├── 00_REVIEW_INDEX.csv
└── 01_H1_problem_definition_<hash>/
    ├── 01_review_files/
    ├── 02_review_payload/
    ├── 02A_GEMINI_AI_STUDIO_PROMPT.md
    ├── 02B_CODEX_REVIEWER_BRIEF.md
    ├── 03A_GEMINI_REVIEW.md
    ├── 03B_CODEX_REVIEW.md
    ├── 03_AI_REVIEW.md
    ├── 04_AI_CROSSCHECK.md
    ├── 04_HUMAN_CHECKLIST.md
    ├── 05_HUMAN_DECISION.md
    └── 06_APPROVE_COMMAND.txt
```

你不需要自己上传文件。到达门禁后，在主 Codex 任务中说“开始审稿”：主 Codex 会控制已登录的 Chrome，把共享载荷交给 Google AI Studio；同一载荷再交给本题独立 Codex 审稿任务。两份回复经 hash 登记并合并后，队员才填写人工清单和结论。完整小白步骤见 [双 AI 审稿指南](docs/DUAL_AI_REVIEW_GUIDE.md)。

```powershell
.\competitions\CUMCM2026\.venv\Scripts\python.exe -m workflow_core.cli.approve `
  --project competitions/CUMCM2026 `
  --run-id <run_id> --gate H1 --human-id M1 `
  --confirm-ai-review --confirm-human-review --notes "已完成 AI 辅助复审和人工核对"

.\competitions\CUMCM2026\.venv\Scripts\python.exe -m workflow_core.cli.run_all `
  --project competitions/CUMCM2026 --profile practice --resume-run <run_id>
```

Codex 不得替队员执行审批命令。H8 必须由两个不同的内部身份分别担任数值模型复核人与论文合规复核人。

## Profile 与退出码

| Profile | 终点 |
| --- | --- |
| `practice` | H5，生成草稿分析结果，不做完整 Audit |
| `audit` | H6，完成比较审计后冻结 analysis run |
| `final` | 以冻结 analysis run 为父运行，完成论文、复现和提交冻结 |

```text
0 = 完成
1 = 质量门禁 ERROR
2 = 配置或程序故障
3 = 主动暂停或等待人工审批
```

正式 final 必须提供冻结分析运行：

```powershell
python -m workflow_core.cli.run_all --project competitions/CUMCM2026 `
  --profile final --source-run <frozen_analysis_run_id>
```

## 当前第一轮状态

已实现最小通用闭环：Schema、资产解析、表格/网络审计、H1-H8、analysis/submission run、不可变输出、逐问故事板、结果卡、摘要矩阵、插件验证梯度、证据与图表门禁、allowlist 打包、冷启动和矿井案例桥接。

P0 质量闭环的核心文件位于：

```text
config/question_storyboard.yml
07_paper/evidence/question_result_cards.csv
07_paper/evidence/abstract_matrix.csv
```

故事板可以在没有结果时填写；结果卡和摘要矩阵只能在冻结 analysis run 已产生真实证据后由队员填写并复核。

暂未实现：MATLAB 适配器、Word 模板适配、时间序列插件及其案例、其余 planned 插件。它们不会生成伪结果，也不会被默认当作正式主模型。

## 隐私与提交 🔒

- 仓库必须保持 Private，只授权正式队员。
- `config/local/`、真实身份映射、敏感词、审批记录和本机路径不进入匿名提交包。
- `09_review_packages/` 是本地内部目录，除说明文件外不进入 Git、提交扫描或匿名支撑材料。
- 大文件、虚拟环境、缓存、LaTeX build 和 run 目录默认不进 Git。
- 本地优秀论文只用于结构与复核方法分析，固定保存在 `00_inbox/reference_papers/`，不得进入配置快照、Git 或匿名包。
- `00_official/` 尚无规则原文快照，因此全国规则当前保持 `pending_confirmation`。
- 自动检查不能替代人工合规复核；最终提交必须双人交叉检查。

队员完整安装步骤见 [TEAM_SETUP.md](TEAM_SETUP.md)，当前项目操作见 [competitions/CUMCM2026/README.md](competitions/CUMCM2026/README.md)。

基于本地优秀论文语料形成的下一轮质量提升方案见 [优秀论文驱动的工作流优化计划](docs/EXCELLENT_PAPER_WORKFLOW_OPTIMIZATION_PLAN.md)。
