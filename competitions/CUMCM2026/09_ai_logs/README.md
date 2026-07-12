# 09_ai_logs

本目录用于记录 AI 工具的实质性使用。

## 记录规则

- 每次实质性使用 AI 记录一行 `ai_usage_log.csv`。
- 完整提示词保存到 `prompts/{record_id}.md`。
- 完整回复保存到 `responses/{record_id}.md`。
- `record_id` 必须唯一，并同时出现在日志、提示词文件和回复文件名中。
- 所有 AI 输出必须经过人工验证。

AI 只能辅助生成、修改、检查和修复，不能替代核心建模判断、结果解释和最终提交决策。
