# Codex 工作规则
## 定位

Codex 负责生成初稿、修改代码、检查逻辑、修复编译和整理证据。Codex 不是参赛队员，不能替代人工建模判断、审批、论文终审或提交决策。

## 不可违反的规则

- 不编造数据、结果、参考文献、官方规则、模型验证或人工复核状态。
- 不修改 `02_raw_data/` 原始文件；运行前后必须核对 SHA256。
- 不把题面条件写成作者假设。
- 不在正式配置、报告、日志和支撑材料中持久化个人绝对路径。
- 不把大型输入、缓存、复现副本或临时目录写入 C 盘。
- 不创建公开竞赛仓库，不启用 GitHub Pages，不公开比赛材料。
- 不自动批准 H1-H8，不代替 M1/M2/M3 执行 `workflow_core.cli.approve`。
- 每次出现审批请求时必须生成对应 `09_review_packages/<run_id>/<order>_<gate>_*` 审核包；不得让队员手工猜测待审文件。
- 用户说“开始审稿”后，主 Codex负责控制已登录的 Chrome 和 Google AI Studio、上传冻结共享载荷并登记完整回复；不得要求用户手工打包上传。
- 第二审稿人必须是本题独立 Codex 任务。没有登记审稿任务时必须暂停，未经用户明确要求不得自动创建任务。
- Gemini 与独立 Codex 任务必须审核相同的 `shared_payload_sha256`，彼此不得读取对方意见；双审完成前不得生成可批准状态。
- Gemini 或 Codex 审稿任务不得修改正式文件、运行正式模型或填写人工审批。主 Codex只能登记回复、汇总分歧并协助人工复核。
- 不修改或删除已完成、冻结或历史 run；变更配置必须创建新 run。
- 不为通过检查而填入虚构数字、结论、文献、claim、证据或 reviewer。
- 不自动填写结果卡和摘要矩阵中的数值；只能依据冻结 analysis run 的 verified evidence 生成待人工复核初稿。
- 不读取、复制或打包 `00_inbox/reference_papers/` 的论文内容作为当前论文正文、结果或参考文献。
- 自动检查不能描述为“已经完全满足官方要求”。

## 架构边界

```text
workflow_core/sdk <- plugins <- cases / competitions
```

- `workflow_core` 不得导入具体插件、案例或比赛模块。
- 插件只能依赖 `workflow_core.sdk`。
- 案例和比赛项目通过受信任注册表选择插件与 runner。
- 项目配置不得提供任意 shell 命令。
- 矿井题的传播、分流、路线前提和空间分段逻辑只能留在案例/比赛层。
- 修改架构后必须运行 AST/import 依赖测试。

## 人工门禁

- H1 未批准：禁止进入需求确认和正式模型卡生成。
- H2 未批准：禁止生成正式处理后数据。
- H3 未批准：禁止正式模型执行。
- H4 未批准：禁止执行验证与 Audit 计划。
- H5 未批准：禁止替代模型比较。
- H6 未批准：禁止冻结 analysis run。
- H7 未批准：禁止匿名支撑材料与最终论文流程。
- H8 未由两个不同 human_id 分角色批准：禁止 submission freeze。

审批对象 hash 变化后，原审批自动失效。Codex 只能生成审批请求和列出待检查内容。

审核包按 H1-H8 固定编号，必须包含精确文件副本、SHA256、Google AI Studio 提示词、Codex 审稿任务交接说明、两份独立回复、交叉核对、人工清单和人工结论。任一 AI 回复、合并结果或人工结论仍有 `PENDING` 标记时不得批准。审核包机制必须保持题目无关，通用核心不得写入矿井题专属字段。

`question_storyboard.yml` 由三个独立投影进入审批：H1 审题目叙事与结论边界，H3 审模型选择与算法前提，H4 审验证选择和未采用理由。不得绕过投影直接声称故事板已批准。

## Run 与证据

- 每次正式运行生成唯一 `run_id`。
- 所有输出写入 `05_model_results/runs/<run_id>/`。
- `completed` 后输出不可变；新增、删除、覆盖均应标记 `tampered`。
- 正式证据只能引用 `frozen` analysis run。
- major claim 必须关联 direct evidence。
- 稳定、鲁棒、准确、最优类 major claim 还必须关联 validation 或 robustness evidence。
- 图表技术检查不能替代人工判断图表是否支持结论。
- 每个小问在 final 中必须有 verified 结果卡和摘要矩阵行，且只能引用 submission run 的冻结 analysis parent。
- 摘要结果句中的每个数值必须存在于该行登记的 verified evidence value 中。

## Waiver 与匿名打包

Waiver 必须精确到 `rule_id + path/artifact + match + expiry`，并保留 `WAIVED_WARNING`。以下错误不可豁免：

```text
raw_data_integrity_failure
identity_information_leak
algorithm_precondition_failure
major_claim_evidence_missing
cold_reproduction_failure
final_artifact_missing
undefined_reference
```

支撑材料只能按 allowlist 正向打包。审批记录、真实姓名映射、`config/local/`、敏感词、本机路径、Git 元数据和内部日志不得进入匿名包。

`09_review_packages/` 同样属于内部资料，禁止进入 Git 和匿名提交包。题目原始附件、优秀论文和本机路径默认不得复制到外部 AI 审核包。

artifact 默认分类为 `internal`。只有显式分类为 `anonymous_candidate` 的冻结 artifact 可以打包；`private_reference` 永远不能进入匿名包。旧 artifact 缺少分类时按 `internal` 处理。

## 修改与验证

- 修改前说明文件范围，修改后报告测试与未解决警告。
- 多文件功能先写测试，再分切片实现。
- 保持 `04_code/run_all.py` 无参数兼容行为。
- 不把 `NOT_IMPLEMENTED` 描述成已完成，不生成替代模型伪结果。
- 论文没有真实结果时保留 `\placeholder{}`；draft 为 WARNING，final 为 ERROR。
