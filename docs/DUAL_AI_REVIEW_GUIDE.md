# 双 AI 审稿小白指南

这套工作流使用两个彼此独立的 AI 审稿人：

1. Google AI Studio 中的 Gemini，重点检查模型、公式、量纲和数值；
2. 本题独立的 Codex 任务，重点通过聊天寻找反例、证据断裂、结论越界和论文风险。

主 Codex 负责组织材料和操作工具，队员负责最终判断。AI 不能批准 H1-H8。

## 每套题目的任务安排

每套题目使用两个 Codex 任务：

- 主工作流任务：读题、建模、代码、图表、论文和总调度；
- 独立审稿任务：只审稿并和队员讨论，不修改正式项目。

不同题目不要共用独立审稿任务，避免旧题上下文影响新题。任务 ID 只保存在本地忽略文件中，不上传 GitHub。

## 到达人工门禁后怎么做

当工作流停在 H1-H8 时，你只需要在主 Codex 任务中输入：

```text
开始审稿
```

主 Codex随后执行：

1. 找到当前门禁最新的审核目录；
2. 验证 `02_review_payload/` 中每个文件的 SHA256；
3. 检查材料是否含身份信息、个人路径或禁止外发内容；
4. 生成 `02_ai_studio_upload/`，为避免扩展名兼容问题，把载荷复制为内容相同的 `.txt` 文件；
5. 告诉队员需要上传的唯一目录和提示词位置；
6. 队员在已登录的 Google AI Studio 中全选上传 `02_ai_studio_upload/`，再粘贴 `02A_GEMINI_AI_STUDIO_PROMPT.md`；
7. 队员将 Gemini 完整回复发回主 Codex，由主 Codex登记到 `03A_GEMINI_REVIEW.md`；
8. 主 Codex把相同载荷和 `02B_CODEX_REVIEWER_BRIEF.md` 发送给独立 Codex 审稿任务；
9. 将独立审稿任务的最终意见登记到 `03B_CODEX_REVIEW.md`；
10. 生成 `03_AI_REVIEW.md` 和 `04_AI_CROSSCHECK.md`，提醒队员处理双方 ERROR、分歧和需要人工确认的事项。

队员不需要自行整理、改名或压缩审核材料，只负责全选上传兼容目录。如果独立审稿任务尚未创建，流程会暂停并征得用户同意，不会伪造审核结果。

## 两个登记命令

正常使用时由主 Codex执行，你不需要手工输入。这里保留命令用于故障恢复：

```powershell
python -m workflow_core.cli.record_ai_review `
  --project competitions/CUMCM2026 --run-id <run_id> --gate H1 `
  --reviewer gemini_ai_studio --input <Gemini回复文件>

python -m workflow_core.cli.record_ai_review `
  --project competitions/CUMCM2026 --run-id <run_id> --gate H1 `
  --reviewer codex_independent_task --input <Codex回复文件>

python -m workflow_core.cli.merge_ai_reviews `
  --project competitions/CUMCM2026 --run-id <run_id> --gate H1
```

每次登记都会保存回复 SHA256。回复被修改后，旧汇总和旧批准自动失效。

## 人工最终检查

两个 AI 都完成后，队员仍需：

1. 阅读两份原始回复和交叉核对；
2. 对每个 ERROR 记录 `fixed`、`false_positive_with_reason`、`accepted_with_limitation` 或 `requires_new_run`；
3. 填写人工清单和人工决定；
4. 由真实队员执行批准命令；
5. H8 由两名不同队员分别完成数值终审和论文合规终审。

## 费用和隐私

- 此模式不调用 Gemini API 或 Claude API，不需要 API 密钥；
- Google AI Studio 使用现有账号权益，仍受账号额度和服务条款约束；
- Codex 独立审稿任务使用现有 Codex 产品额度；
- 审核材料只发送脱敏共享载荷；
- 私有优秀论文、真实身份映射、本地路径、审批记录和敏感词配置不得外发；
- 如果当届比赛规则禁止使用外部 AI，必须停止 AI 审核并改为纯人工复核。
