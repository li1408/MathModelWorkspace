# 10_submission_check

本目录保存最终提交前的检查清单、规则配置、敏感词配置、精确豁免表和自动检查脚本。

自动检查只能发现常见风险，不能替代队员对 2026 年全国及所在赛区正式通知的人工合规复核。

## 文件说明

- `check_submission.py`：提交前自动检查脚本。
- `submission_rules.yml`：页数、文件大小、必要文件、扫描范围等规则。所有官方限制都需要赛前复核。
- `sensitive_terms.example.yml`：敏感词配置示例，可以复制为本地文件。
- `sensitive_terms.local.yml`：队伍自行填写的姓名、学校、教师、学号和联系方式等敏感词；该文件被 `.gitignore` 排除。
- `allowlist.yml`：仅用于明确误报，必须按规则、路径和具体匹配内容精确豁免。
- `final_checklist.md`：最终提交前人工检查清单。

## 运行方式

```powershell
python 10_submission_check/check_submission.py --root . --mode draft
python 10_submission_check/check_submission.py --root . --mode final
```

`draft` 模式下，缺少 `sensitive_terms.local.yml` 会报告 `WARNING`；`final` 模式下，缺少本地敏感词文件、文件为空或仍含示例值会报告 `ERROR`。

退出码含义：

- `0`：没有 `ERROR`。
- `1`：存在至少一个 `ERROR`。
- `2`：脚本或配置失败。
