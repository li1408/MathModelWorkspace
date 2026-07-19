"""Create path-neutral, hash-bound review packages for gates H1-H8."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflow_core.evidence.artifacts import sha256_file
from workflow_core.orchestration.run_context import RunContext
from workflow_core.review.status import (
    PENDING_AI_MARKER,
    PENDING_HUMAN_MARKER,
    inspect_review_package,
)
from workflow_core.review.queue import write_review_queue
from workflow_core.review.dual import (
    CODEX_REVIEWER_MODEL,
    GEMINI_MODEL,
    validate_shared_payload,
)


GATE_METADATA = {
    "H1": (1, "problem_definition", "题目理解与逐问叙事", [
        "Q1-Qn 是否完整覆盖题目要求",
        "输入、输出、目标和结论边界是否准确",
        "题面条件是否被误写成作者假设",
    ]),
    "H2": (2, "data_preprocessing", "数据审计与预处理", [
        "原始数据 hash、只读性和字段理解是否正确",
        "预处理操作是否可复现且不会修改原始数据",
        "缺失值、异常值和单位处理是否有依据",
    ]),
    "H3": (3, "model_design", "模型选择与假设", [
        "主模型选择理由是否针对本题而非模型名称堆叠",
        "高风险假设、算法前提和失败场景是否完整",
        "候选模型和淘汰理由是否合理",
    ]),
    "H4": (4, "validation_plan", "验证计划与审计预算", [
        "验证是否覆盖所有活动插件要求和高风险假设",
        "验收指标、阈值和失败 fallback 是否明确",
        "未采用的验证是否有人工可审查理由",
    ]),
    "H5": (5, "baseline_validation", "基线结果与基本不变量", [
        "模型输出是否满足守恒、可行性和输出合同",
        "实现是否与模型定义一致",
        "异常、空白输出或失败状态是否被掩盖",
    ]),
    "H6": (6, "alternatives_comparison", "替代模型与结构比较", [
        "比较对象、单位、时间窗口和指标是否一致",
        "替代模型是否改变主要决策",
        "结论范围是否根据结构敏感性适当收窄",
    ]),
    "H7": (7, "paper_evidence", "论文、证据与图表", [
        "摘要和正文数字是否能追溯到冻结证据",
        "强结论是否具备直接证据和验证证据",
        "图表、符号、单位、引用和论文叙事是否一致",
    ]),
    "H8": (8, "final_submission", "最终提交与双人复核", [
        "最终 PDF、支撑材料、hash 和必要文件是否完整",
        "身份、学校、本机路径和内部记录是否已排除",
        "数值终审与论文合规终审是否由不同队员完成",
    ]),
}

FORBIDDEN_SOURCE_PARTS = {
    "00_inbox",
    "reference_papers",
    "approvals",
    ".git",
    "09_ai_logs",
}
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".yml", ".yaml", ".tex", ".py", ".ps1"}
ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:[\\/][^\r\n\"']+|/(?:Users|home)/[^\r\n\"']+)")


class ReviewPackageError(RuntimeError):
    """Raised when a gate review package would be unsafe or unverifiable."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _fingerprint(hashes: dict[str, str]) -> str:
    payload = json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:10]


def _safe_name(value: str) -> str:
    rendered = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return rendered or "ARTIFACT"


def _source_locator(project_root: Path, source: Path) -> str:
    project = project_root.resolve()
    resolved = source.resolve()
    try:
        relative = resolved.relative_to(project)
    except ValueError as exc:
        raise ReviewPackageError("Review sources must stay inside the project directory.") from exc
    lower_parts = tuple(part.lower() for part in relative.parts)
    if any(part in FORBIDDEN_SOURCE_PARTS for part in lower_parts):
        raise ReviewPackageError(
            f"Private or internal-only source cannot enter a review package: {relative.as_posix()}"
        )
    if len(lower_parts) >= 2 and lower_parts[:2] == ("config", "local"):
        raise ReviewPackageError("Machine-local configuration cannot enter a review package.")
    return f"project://{relative.as_posix()}"


def _check_text_privacy(source: Path) -> None:
    if source.suffix.lower() not in TEXT_SUFFIXES:
        return
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeError:
        return
    if ABSOLUTE_PATH.search(text):
        raise ReviewPackageError(
            f"Personal absolute path found in review source: {source.name}"
        )


def _ai_prompt(gate_id: str, title: str, focus: list[str], ai_tool: str) -> str:
    focus_lines = "\n".join(f"{index}. {item}；" for index, item in enumerate(focus, start=1))
    return f"""# {ai_tool} 独立审核提示词

你是数学建模项目的独立反方复审员。请只审核本目录 `01_review_files/` 中的材料，本次门禁为 `{gate_id}`：{title}。

必须遵守：

- 不编造数据、结果、文献、官方规则或人工审批；
- 不把 AI 意见描述为最终批准；
- 每个发现必须指出文件名、字段或具体位置；
- 信息不足时写“需要人工确认”，不要自行补全；
- 重点尝试推翻不充分的模型选择、验证和结论。

本门禁重点：

{focus_lines}

请严格按以下结构输出：

```text
审核结论：存在问题 / 未发现阻断项（不能写“批准”）

ERROR
- [文件或字段] 问题、影响、必须采取的修复

WARNING
- [文件或字段] 风险、影响、建议处理

INFO
- 可选改进

需要人工确认
- 无法由现有材料判断的事项

逐项核对
- 列出本次门禁重点的核对结果
```

完成后，将完整回复保存到 `03_AI_REVIEW.md`，并按 `07_AI_LOG_GUIDE.md` 登记本次 AI 使用。
"""


def _gemini_prompt(gate_id: str, title: str, focus: list[str], payload_hash: str) -> str:
    focus_lines = "\n".join(f"{index}. {item}；" for index, item in enumerate(focus, start=1))
    return f"""# Gemini 模型与数值独立审核

你是数学建模项目的模型与数值审稿人。本次门禁为 `{gate_id}`：{title}。
只审核 `02_review_payload/` 中的共享载荷；共享载荷 SHA256 为：

`{payload_hash}`

不得联网、运行工具、访问仓库其他目录、编造数据或代替人工批准。不得读取另一个审稿人的结果。
每个发现必须指出审核材料中的文件或字段；确定性 hash、守恒检验和程序合同优先于 AI 意见。

审核重点：

{focus_lines}

请严格使用以下结构，完整回复保存到 `03A_GEMINI_REVIEW.md`：

```text
审核结论：存在问题 / 未发现阻断项（不得写“批准”）

ERROR
- [文件或字段] 问题、证据、影响、必须采取的修复

WARNING
- [文件或字段] 风险、证据、影响、建议处理

INFO
- 可选改进

需要人工确认
- 现有材料无法判断的事项

逐项核对
- 本门禁重点的核对结果
```
"""


def _codex_reviewer_brief(
    gate_id: str, title: str, focus: list[str], payload_hash: str
) -> str:
    focus_lines = "\n".join(f"- {item}" for item in focus)
    return f"""# Codex 独立审稿任务交接说明

你是本题专用的独立反方审稿人。本次门禁为 `{gate_id}`：{title}。
只审核 `02_review_payload/` 中的共享载荷；不得读取另一个审稿人的结果，
不得修改正式项目文件、运行正式模型或代替队员批准。共享载荷 SHA256 为：

`{payload_hash}`

请在独立 Codex 任务的聊天窗口中主动协助人工审稿，并重点寻找反例、遗漏条件、
证据断裂、结论越界和匿名合规风险：

{focus_lines}

最终审核意见必须严格使用以下 Markdown 结构，并由主工作流保存为
`03B_CODEX_REVIEW.md`：

```text
审核结论：存在问题 / 未发现阻断项（不得写“批准”）

ERROR
- [文件或字段] 问题、证据、影响、必须采取的修复

WARNING
- [文件或字段] 风险、证据、影响、建议处理

INFO
- 可选改进

需要人工确认
- 通过聊天需要队员核实的事项

逐项核对
- 本门禁重点的核对结果
```
"""


def _human_checklist(gate_id: str, title: str, focus: list[str]) -> str:
    focus_lines = "\n".join(f"- [ ] {item}" for item in focus)
    h8 = "\n- [ ] 两名不同队员分别完成数值终审与论文合规终审" if gate_id == "H8" else ""
    return f"""# 人工审核清单

门禁：`{gate_id}` {title}

- [ ] 已逐个打开 `01_review_files/` 中的文件
- [ ] 已核对 `package_manifest.json` 中的 SHA256
- [ ] 已阅读 `03A_GEMINI_REVIEW.md`、`03B_CODEX_REVIEW.md` 和 `04_AI_CROSSCHECK.md`
- [ ] 两个 AI 的每项 ERROR 均已在人工结论中逐项登记处理
- [ ] 双方结论不一致时已经完成独立人工裁决
- [ ] 没有让 AI 替代人工模型判断或批准门禁
{focus_lines}{h8}
- [ ] 人工结论已写入 `05_HUMAN_DECISION.md`
"""


def _approval_command(project_root: Path, context: RunContext, gate_id: str) -> str:
    repository_root = Path(__file__).resolve().parents[2]
    try:
        project_arg = project_root.resolve().relative_to(repository_root).as_posix()
    except ValueError:
        project_arg = "."
    project_python = project_root.resolve() / ".venv/Scripts/python.exe"
    if project_python.is_file():
        try:
            python_relative = project_python.relative_to(repository_root)
            python_command = "& '.\\" + str(python_relative).replace("/", "\\") + "'"
        except ValueError:
            python_command = "python"
    else:
        python_command = "python"
    base = (
        f"{python_command} -m workflow_core.cli.approve "
        f"--project {project_arg} --run-id {context.run_id} --gate {gate_id} "
    )
    if gate_id == "H8":
        return (
            "# 必须由两个不同队员在人工审核完成后分别执行：\n"
            + base
            + "--human-id M1 --reviewer-role model_numeric_reviewer --confirm-ai-review --confirm-human-review\n"
            + base
            + "--human-id M2 --reviewer-role paper_compliance_reviewer --confirm-ai-review --confirm-human-review\n"
        )
    return (
        "# 仅在 AI 审核和人工审核均完成后，由实际队员执行；请替换 M1：\n"
        + base
        + '--human-id M1 --confirm-ai-review --confirm-human-review --notes "已完成 AI 辅助复审和人工复核"\n'
    )


def validate_review_package_for_approval(
    project_root: Path,
    request: dict[str, Any],
    *,
    confirm_ai_review: bool,
) -> None:
    """Require completed AI and human review files for new-style approval requests."""
    relative_value = request.get("review_package")
    if not relative_value:
        return
    if not confirm_ai_review:
        raise ReviewPackageError("Use --confirm-ai-review after reading the complete AI review.")
    relative = Path(str(relative_value))
    if relative.is_absolute() or ".." in relative.parts:
        raise ReviewPackageError("Review package path must be project-relative and safe.")
    project = project_root.resolve()
    package = (project / relative).resolve()
    try:
        package.relative_to(project / "09_review_packages")
    except ValueError as exc:
        raise ReviewPackageError("Review package must stay under 09_review_packages.") from exc
    manifest_path = package / "package_manifest.json"
    if not manifest_path.is_file():
        raise ReviewPackageError("Review package manifest is missing.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if request.get("gate_id") and manifest.get("gate_id") != request.get("gate_id"):
        raise ReviewPackageError("Review package gate does not match the approval request.")
    if manifest.get("artifact_hashes") != request.get("artifact_hashes"):
        raise ReviewPackageError("Review package hashes do not match the approval request.")
    for record in manifest.get("files", []):
        copied = package / record["copied_path"]
        if not copied.is_file() or sha256_file(copied) != record["copied_sha256"]:
            raise ReviewPackageError("A file in the review package was changed after packaging.")
    if manifest.get("review_policy_version") == 2:
        try:
            validate_shared_payload(package)
        except Exception as exc:
            raise ReviewPackageError(f"Shared review payload is invalid: {exc}") from exc
    live_status = inspect_review_package(package)
    if not live_status.get("review_complete"):
        details = "; ".join(str(item) for item in live_status.get("issues", []))
        raise ReviewPackageError(
            f"Review package is not ready: {live_status.get('status')}. {details}".rstrip()
        )


def review_completion_hashes(
    project_root: Path,
    request: dict[str, Any],
    *,
    confirm_ai_review: bool,
) -> dict[str, str]:
    """Return hashes that bind completed AI and human review text to approval."""
    if not request.get("review_package"):
        return {}
    validate_review_package_for_approval(
        project_root,
        request,
        confirm_ai_review=confirm_ai_review,
    )
    package = project_root.resolve() / str(request["review_package"])
    manifest = json.loads((package / "package_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("review_policy_version") == 2:
        return {
            "GEMINI-REVIEW": sha256_file(package / "03A_GEMINI_REVIEW.md"),
            "CODEX-REVIEW": sha256_file(package / "03B_CODEX_REVIEW.md"),
            "AI-CROSSCHECK": sha256_file(package / "04_AI_CROSSCHECK.md"),
            "AI-REVIEW": sha256_file(package / "03_AI_REVIEW.md"),
            "HUMAN-DECISION": sha256_file(package / "05_HUMAN_DECISION.md"),
        }
    return {
        "AI-REVIEW": sha256_file(package / "03_AI_REVIEW.md"),
        "HUMAN-DECISION": sha256_file(package / "05_HUMAN_DECISION.md"),
    }


def update_review_package_status(
    project_root: Path,
    request: dict[str, Any],
    status: str,
) -> None:
    """Update the local review index after an approval decision is recorded."""
    relative_value = request.get("review_package")
    if not relative_value:
        return
    package = (project_root.resolve() / str(relative_value)).resolve()
    manifest_path = package / "package_manifest.json"
    if not manifest_path.is_file():
        raise ReviewPackageError("Review package manifest is missing.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = status
    manifest["review_status_updated_at"] = _utc_now()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_summary(package.parent)
    write_review_queue(project_root)


def _write_summary(run_root: Path) -> None:
    rows = []
    for manifest_path in sorted(run_root.glob("[0-9][0-9]_H*/package_manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        package_relative = manifest_path.parent.relative_to(run_root).as_posix()
        rows.append(
            {
                "order": manifest["order"],
                "gate_id": manifest["gate_id"],
                "title": manifest["title"],
                "package": package_relative,
                "status": manifest.get("status", "pending_ai_and_human_review"),
                "ai_review": f"{package_relative}/03_AI_REVIEW.md",
                "human_review": f"{package_relative}/05_HUMAN_DECISION.md",
            }
        )
    with (run_root / "00_REVIEW_INDEX.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("order", "gate_id", "title", "package", "status", "ai_review", "human_review"),
        )
        writer.writeheader()
        writer.writerows(rows)


def prepare_review_package(
    project_root: Path,
    context: RunContext,
    gate_id: str,
    artifact_paths: dict[str, Path],
    expected_hashes: dict[str, str],
    *,
    ai_tool: str = "Gemini",
    review_policy_version: int = 1,
) -> Path:
    """Copy exact gate artifacts into an ordered local AI+human review package."""
    if gate_id not in GATE_METADATA:
        raise ReviewPackageError(f"Unsupported review gate: {gate_id}")
    if set(artifact_paths) != set(expected_hashes) or not artifact_paths:
        raise ReviewPackageError("Review artifact labels and expected hashes must match.")
    project = project_root.resolve()
    order, slug, title, focus = GATE_METADATA[gate_id]
    fingerprint = _fingerprint(expected_hashes)
    run_root = project / "09_review_packages" / context.run_id
    package = run_root / f"{order:02d}_{gate_id}_{slug}_{fingerprint}"
    manifest_path = package / "package_manifest.json"
    if package.exists():
        if not manifest_path.is_file():
            raise ReviewPackageError("Existing review package has no manifest; it was not overwritten.")
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("artifact_hashes") != expected_hashes:
            raise ReviewPackageError("Existing review package fingerprint does not match its manifest.")
        for record in existing.get("files", []):
            copied = package / record["copied_path"]
            if not copied.is_file() or sha256_file(copied) != record["copied_sha256"]:
                raise ReviewPackageError("A copied review artifact was modified; create a new run or restore it.")
        write_review_queue(project)
        return package

    copied_dir = package / "01_review_files"
    copied_dir.mkdir(parents=True)
    records: list[dict[str, Any]] = []
    for index, (label, source_value) in enumerate(artifact_paths.items(), start=1):
        source = source_value.resolve()
        if not source.is_file():
            raise ReviewPackageError(f"Review source is missing: {label}")
        locator = _source_locator(project, source)
        _check_text_privacy(source)
        actual_hash = sha256_file(source)
        if actual_hash.lower() != expected_hashes[label].lower():
            raise ReviewPackageError(f"Review source hash changed before packaging: {label}")
        source_token = _safe_name(source.stem)
        destination_name = (
            f"{index:02d}_{_safe_name(label)}__{source_token}{source.suffix.lower()}"
        )
        destination = copied_dir / destination_name
        shutil.copy2(source, destination)
        copied_hash = sha256_file(destination)
        records.append(
            {
                "order": index,
                "artifact_label": label,
                "source_locator": locator,
                "source_sha256": actual_hash,
                "copied_path": destination.relative_to(package).as_posix(),
                "copied_sha256": copied_hash,
                "size_bytes": destination.stat().st_size,
            }
        )

    if review_policy_version == 1:
        manifest = {
            "schema_version": 1,
            "run_id": context.run_id,
            "gate_id": gate_id,
            "order": order,
            "title": title,
            "generated_at": _utc_now(),
            "artifact_hashes": expected_hashes,
            "files": records,
            "ai_tool": ai_tool,
            "status": "pending_ai_and_human_review",
        }
        (package / "00_README.md").write_text(
            f"# {gate_id} 审核包\n\n请按顺序完成 AI 审核、人工清单和人工结论。\n",
            encoding="utf-8",
        )
        (package / "02_AI_PROMPT.md").write_text(
            _ai_prompt(gate_id, title, focus, ai_tool), encoding="utf-8"
        )
        (package / "03_AI_REVIEW.md").write_text(
            "# AI 审核完整记录\n\n[[PENDING_AI_REVIEW]]\n\n"
            "请将 Gemini 的完整原始回复粘贴在此处。\n",
            encoding="utf-8",
        )
        (package / "04_HUMAN_CHECKLIST.md").write_text(
            _human_checklist(gate_id, title, focus), encoding="utf-8"
        )
        (package / "05_HUMAN_DECISION.md").write_text(
            """# 人工审核结论

[[PENDING_HUMAN_DECISION]]

- 审核人内部编号：待填写
- 审核日期：待填写
- 人工决定：待填写（批准 / 要求修改 / 拒绝）
- ERROR 处理情况：待填写
- WARNING 处理情况：待填写
- 人工额外发现：待填写
- 结论与限制：待填写
""",
            encoding="utf-8",
        )
        (package / "06_APPROVE_COMMAND.txt").write_text(
            _approval_command(project, context, gate_id), encoding="utf-8"
        )
        (package / "07_AI_LOG_GUIDE.md").write_text(
            "# AI 使用日志\n\n完成后按项目规则登记本次实质性 AI 使用。\n",
            encoding="utf-8",
        )
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        _write_summary(run_root)
        write_review_queue(project)
        return package
    if review_policy_version != 2:
        raise ReviewPackageError("review_policy_version must be 1 or 2.")

    payload_dir = package / "02_review_payload"
    payload_dir.mkdir()
    payload_files: list[dict[str, Any]] = []
    for record in records:
        source = package / record["copied_path"]
        destination = payload_dir / source.name
        shutil.copy2(source, destination)
        payload_files.append(
            {
                "artifact_label": record["artifact_label"],
                "relative_path": destination.relative_to(payload_dir).as_posix(),
                "sha256": sha256_file(destination),
                "size_bytes": destination.stat().st_size,
            }
        )
    payload_fingerprint = hashlib.sha256(
        json.dumps(
            payload_files, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    payload_manifest = {
        "schema_version": 1,
        "shared_payload_sha256": payload_fingerprint,
        "files": payload_files,
    }
    (payload_dir / "payload_manifest.json").write_text(
        json.dumps(payload_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "schema_version": 1,
        "review_policy_version": 2,
        "run_id": context.run_id,
        "gate_id": gate_id,
        "order": order,
        "title": title,
        "ai_tool": "Google AI Studio / Gemini + Codex independent task",
        "required_ai_reviewers": ["gemini_ai_studio", "codex_independent_task"],
        "shared_payload_sha256": payload_fingerprint,
        "ai_reviews": [
            {
                "reviewer_id": "gemini_ai_studio",
                "provider": "google_ai_studio",
                "model_id": GEMINI_MODEL,
                "review_role": "model_numeric_reviewer",
                "review_file": "03A_GEMINI_REVIEW.md",
                "interaction_mode": "codex_browser_operator",
                "review_sha256": None,
                "completed_at": None,
            },
            {
                "reviewer_id": "codex_independent_task",
                "provider": "openai_codex",
                "model_id": CODEX_REVIEWER_MODEL,
                "review_role": "paper_evidence_adversarial_reviewer",
                "review_file": "03B_CODEX_REVIEW.md",
                "interaction_mode": "independent_task_chat",
                "review_sha256": None,
                "completed_at": None,
            },
        ],
        "status": "pending_ai_and_human_review",
        "generated_at": _utc_now(),
        "artifact_hashes": expected_hashes,
        "files": records,
    }
    (package / "00_README.md").write_text(
        f"""# {gate_id} 审核包：{title}

1. 在主 Codex 任务中说“开始审稿”，由 Codex 控制已登录的 Chrome 和 Google AI Studio；
2. Codex 上传 `02_review_payload/`、使用 `02A_GEMINI_AI_STUDIO_PROMPT.md` 并保存 Gemini 回复；
3. 将同一载荷和 `02B_CODEX_REVIEWER_BRIEF.md` 发送到本题独立 Codex 审稿任务；
4. 两份独立审核完成后生成 `03_AI_REVIEW.md` 与 `04_AI_CROSSCHECK.md`；
5. 队员完成 `04_HUMAN_CHECKLIST.md` 与 `05_HUMAN_DECISION.md`；
6. 有 ERROR 时先处理并登记，源材料改变时必须创建新 run；
7. 全部人工复核完成后，实际队员才可使用 `06_APPROVE_COMMAND.txt`。

两个 AI 彼此独立，不能读取对方回复，也不能批准 H1-H8。本目录不得放入匿名提交包。
""",
        encoding="utf-8",
    )
    (package / "02A_GEMINI_AI_STUDIO_PROMPT.md").write_text(
        _gemini_prompt(gate_id, title, focus, payload_fingerprint), encoding="utf-8"
    )
    (package / "02B_CODEX_REVIEWER_BRIEF.md").write_text(
        _codex_reviewer_brief(gate_id, title, focus, payload_fingerprint), encoding="utf-8"
    )
    (package / "03A_GEMINI_REVIEW.md").write_text(
        "# Gemini 模型与数值审核\n\n[[PENDING_GEMINI_REVIEW]]\n\n"
        "请用 Google AI Studio 的完整原始回复替换本标记。\n",
        encoding="utf-8",
    )
    (package / "03B_CODEX_REVIEW.md").write_text(
        "# Codex 独立反方审核\n\n[[PENDING_CODEX_REVIEW]]\n\n"
        "创建本题独立审稿任务后，由主工作流发送共享载荷并保存最终聊天结论。\n",
        encoding="utf-8",
    )
    (package / "03_AI_REVIEW.md").write_text(
        "# 双 AI 审核完整记录\n\n[[PENDING_AI_MERGE]]\n\n"
        "Gemini 与独立 Codex 审稿任务均完成后由合并命令生成，禁止手工填写。\n",
        encoding="utf-8",
    )
    (package / "04_AI_CROSSCHECK.md").write_text(
        "# 双 AI 交叉审核\n\n[[PENDING_AI_MERGE]]\n",
        encoding="utf-8",
    )
    (package / "04_HUMAN_CHECKLIST.md").write_text(
        _human_checklist(gate_id, title, focus), encoding="utf-8"
    )
    (package / "05_HUMAN_DECISION.md").write_text(
        """# 人工审核结论

[[PENDING_HUMAN_DECISION]]

- 审核人内部编号：待填写
- 审核日期：待填写
- 人工决定：待填写（批准 / 要求修改 / 拒绝）
- AI ERROR 处理情况：待填写（fixed / false_positive_with_reason / accepted_with_limitation / requires_new_run）
- AI WARNING 处理情况：待填写
- 人工额外发现：待填写
- 结论与限制：待填写

只有实际队员可以填写本文件并执行批准命令。
""",
        encoding="utf-8",
    )
    (package / "06_APPROVE_COMMAND.txt").write_text(
        _approval_command(project, context, gate_id), encoding="utf-8"
    )
    (package / "07_AI_LOG_GUIDE.md").write_text(
        f"""# AI 使用日志

本次 Gemini 与独立 Codex 审稿任务双审均属于实质性 AI 使用。完成后必须分别登记：

1. 在 `09_ai_logs/ai_usage_log.csv` 增加一行；
2. 将发送给两个 AI 的完整提示词保存到 `09_ai_logs/prompts/<record_id>.md`；
3. 将完整回复保存到 `09_ai_logs/responses/<record_id>.md`；
4. `record_id` 建议包含日期、提供方、门禁和 run 短编号；
5. AI 日志是内部记录，不进入匿名支撑材料。
""",
        encoding="utf-8",
    )
    (package / "review_usage.jsonl").write_text("", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_summary(run_root)
    write_review_queue(project)
    return package
