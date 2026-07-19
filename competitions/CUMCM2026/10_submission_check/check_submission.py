#!/usr/bin/env python
"""Submission preflight checker for the CUMCM2026 workspace."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


CODE_DIR = Path(__file__).resolve().parents[1] / "04_code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))


SEVERITIES = ("ERROR", "WARNING", "INFO")
PLACEHOLDER_RE = re.compile(r"\[\[PLACEHOLDER:[^\]]*\]\]")
PLACEHOLDER_MACRO_RE = re.compile(
    r"\\(?:placeholder|cumcmplaceholder|cumcminlineplaceholder|cumcmmathplaceholder)\{([^}]*)\}"
)
ABSOLUTE_PATH_RE = re.compile(
    r"((?<![A-Za-z0-9_])[A-Za-z]:\\[^\\\s\]\)\}\"']+\\[^\s\]\)\}\"']+|/(?:Users|home|mnt|var|tmp)/[^\s\]\)\}\"']+)"
)
INPUT_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")
GRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
BIB_RE = re.compile(r"\\bibliography\{([^}]+)\}")


@dataclass(frozen=True)
class Issue:
    severity: str
    rule: str
    path: str
    message: str
    match: str = ""


class ConfigError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise ConfigError("PyYAML is not installed. Install requirements.txt first.")
    if not path.exists():
        raise ConfigError(f"Missing config file: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ConfigError(f"Cannot parse YAML config {path}: {exc}") from exc
    return data or {}


def relpath(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def is_in_excluded_dir(rel: str, excluded_dirs: Iterable[str]) -> bool:
    normalized = rel.replace("\\", "/")
    for item in excluded_dirs:
        item = str(item).strip("/")
        if normalized == item or normalized.startswith(item + "/"):
            return True
    return False


def iter_files(root: Path, rules: dict[str, Any]) -> Iterable[Path]:
    excluded = rules.get("scan", {}).get("excluded_dirs", [])
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if not is_in_excluded_dir(relpath(root, current / dirname), excluded)
        ]
        for filename in filenames:
            yield current / filename


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="gbk")
        except UnicodeDecodeError:
            return None
    except OSError:
        return None


def issue_allowed(issue: Issue, allow_entries: list[dict[str, Any]]) -> bool:
    for entry in allow_entries:
        if entry.get("rule") != issue.rule:
            continue
        if not fnmatch.fnmatch(issue.path, str(entry.get("path", ""))):
            continue
        if str(entry.get("match", "")) != issue.match:
            continue
        return True
    return False


def add_issue(
    issues: list[Issue],
    allow_entries: list[dict[str, Any]],
    severity: str,
    rule: str,
    path: str,
    message: str,
    match: str = "",
) -> None:
    issue = Issue(severity=severity, rule=rule, path=path, message=message, match=match)
    if not issue_allowed(issue, allow_entries):
        issues.append(issue)


def configured_sensitive_terms(sensitive: dict[str, Any]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    terms = sensitive.get("terms", {})
    if not isinstance(terms, dict):
        return result
    for category, values in terms.items():
        for value in values or []:
            value = str(value).strip()
            if value:
                result.append((str(category), value))
    return result


def load_sensitive_config(
    root: Path,
    sensitive_path: Path,
    mode: str,
    allow_entries: list[dict[str, Any]],
    issues: list[Issue],
) -> dict[str, Any]:
    rel = relpath(root, sensitive_path)
    severity = "ERROR" if mode == "final" else "WARNING"
    if not sensitive_path.exists():
        add_issue(
            issues,
            allow_entries,
            severity,
            "sensitive_terms_local_missing",
            rel,
            "Local sensitive terms file is missing. Copy sensitive_terms.example.yml to sensitive_terms.local.yml and replace examples.",
            rel,
        )
        return {}
    sensitive = load_yaml(sensitive_path)
    terms = configured_sensitive_terms(sensitive)
    if sensitive.get("contains_example_values") is True:
        add_issue(
            issues,
            allow_entries,
            severity,
            "sensitive_terms_contains_examples",
            rel,
            "Local sensitive terms file still declares example values.",
            "contains_example_values: true",
        )
    if not terms:
        add_issue(
            issues,
            allow_entries,
            severity,
            "sensitive_terms_empty",
            rel,
            "Local sensitive terms file contains no terms; identity scanning is limited.",
            rel,
        )
    return sensitive


def text_files(root: Path, rules: dict[str, Any]) -> Iterable[tuple[Path, str, str]]:
    extensions = set(rules.get("scan", {}).get("text_extensions", []))
    for path in iter_files(root, rules):
        if path.suffix.lower() not in extensions:
            continue
        text = read_text(path)
        if text is None:
            continue
        yield path, relpath(root, path), text


def scan_sensitive_terms(
    root: Path,
    rules: dict[str, Any],
    sensitive: dict[str, Any],
    allow_entries: list[dict[str, Any]],
    issues: list[Issue],
    mode: str,
) -> None:
    terms = configured_sensitive_terms(sensitive)
    if not terms:
        return
    config_paths = {
        "10_submission_check/sensitive_terms.example.yml",
        "10_submission_check/sensitive_terms.local.yml",
        "10_submission_check/sensitive_terms.local.yaml",
        "10_submission_check/allowlist.yml",
        "10_submission_check/submission_rules.yml",
    }
    for _path, rel, text in text_files(root, rules):
        if rel in config_paths:
            continue
        for category, term in terms:
            if term in text:
                add_issue(
                    issues,
                    allow_entries,
                    "ERROR",
                    "sensitive_terms",
                    rel,
                    f"Sensitive term from category '{category}' found.",
                    term,
                )


def scan_text_patterns(
    root: Path,
    rules: dict[str, Any],
    allow_entries: list[dict[str, Any]],
    issues: list[Issue],
    mode: str,
) -> None:
    placeholder_severity = "ERROR" if mode == "final" else "WARNING"
    path_severity = "ERROR" if mode == "final" else "WARNING"
    for _path, rel, text in text_files(root, rules):
        for match in PLACEHOLDER_RE.findall(text):
            add_issue(
                issues,
                allow_entries,
                placeholder_severity,
                "placeholder",
                rel,
                "Unresolved placeholder marker found.",
                match,
            )
        for match in PLACEHOLDER_MACRO_RE.findall(text):
            add_issue(
                issues,
                allow_entries,
                placeholder_severity,
                "placeholder",
                rel,
                "Unresolved LaTeX placeholder macro found.",
                match,
            )
        for match in ABSOLUTE_PATH_RE.findall(text):
            add_issue(
                issues,
                allow_entries,
                path_severity,
                "absolute_path",
                rel,
                "Absolute local path found.",
                match,
            )


def check_required_files(
    root: Path,
    rules: dict[str, Any],
    allow_entries: list[dict[str, Any]],
    issues: list[Issue],
    mode: str,
) -> None:
    required = list(rules.get("required_files", {}).get("draft", []))
    if mode == "final":
        required += list(rules.get("required_files", {}).get("final", []))
    for rel in required:
        if not (root / rel).exists():
            add_issue(
                issues,
                allow_entries,
                "ERROR",
                "required_file_missing",
                rel,
                "Required file is missing.",
                rel,
            )


def candidate_input_paths(tex_file: Path, reference: str) -> list[Path]:
    raw = Path(reference)
    candidates = [tex_file.parent / raw]
    if raw.suffix == "":
        candidates.append(tex_file.parent / f"{reference}.tex")
    return candidates


def candidate_graphic_paths(root: Path, tex_file: Path, reference: str, rules: dict[str, Any]) -> list[Path]:
    raw = Path(reference)
    bases = [tex_file.parent] + [root / p for p in rules.get("latex", {}).get("graphics_paths", [])]
    exts = rules.get("latex", {}).get("graphics_extensions", [".pdf", ".png", ".jpg", ".jpeg"])
    candidates: list[Path] = []
    for base in bases:
        if raw.suffix:
            candidates.append(base / raw)
        else:
            candidates.extend(base / f"{reference}{ext}" for ext in exts)
    return candidates


def any_exists(paths: Iterable[Path]) -> bool:
    return any(path.exists() for path in paths)


def scan_latex_sources(
    root: Path,
    rules: dict[str, Any],
    allow_entries: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    paper_dir = root / rules.get("latex", {}).get("paper_dir", "07_paper")
    if not paper_dir.exists():
        return
    for tex_file in paper_dir.rglob("*.tex"):
        text = read_text(tex_file) or ""
        rel = relpath(root, tex_file)
        for reference in INPUT_RE.findall(text):
            if not any_exists(candidate_input_paths(tex_file, reference)):
                add_issue(
                    issues,
                    allow_entries,
                    "ERROR",
                    "latex_missing_input",
                    rel,
                    "LaTeX input/include target is missing.",
                    reference,
                )
        for reference in GRAPHICS_RE.findall(text):
            if not any_exists(candidate_graphic_paths(root, tex_file, reference, rules)):
                add_issue(
                    issues,
                    allow_entries,
                    "ERROR",
                    "latex_missing_graphic",
                    rel,
                    "LaTeX includegraphics target is missing.",
                    reference,
                )
        for bibliography in BIB_RE.findall(text):
            for name in [item.strip() for item in bibliography.split(",") if item.strip()]:
                candidate = tex_file.parent / f"{name}.bib"
                if not candidate.exists():
                    add_issue(
                        issues,
                        allow_entries,
                        "ERROR",
                        "latex_missing_bibliography",
                        rel,
                        "BibTeX bibliography file is missing.",
                        f"{name}.bib",
                    )


def scan_latex_log(
    root: Path,
    rules: dict[str, Any],
    allow_entries: list[dict[str, Any]],
    issues: list[Issue],
    mode: str,
) -> None:
    log_rel = rules.get("latex", {}).get("log_file", "07_paper/build/main.log")
    log_path = root / log_rel
    if not log_path.exists():
        add_issue(
            issues,
            allow_entries,
            "WARNING" if mode == "final" else "INFO",
            "latex_log_missing",
            log_rel,
            "LaTeX build log is not available; log-based checks were skipped.",
            log_rel,
        )
        return
    text = read_text(log_path) or ""
    severity = "ERROR" if mode == "final" else "WARNING"
    patterns = [
        (re.compile(r"! LaTeX Error: File `([^']+)' not found\."), "latex_log_missing_file"),
        (re.compile(r"LaTeX Warning: Reference `([^']+)' .* undefined"), "latex_log_undefined_reference"),
        (re.compile(r"LaTeX Warning: Citation `([^']+)' .* undefined"), "latex_log_undefined_citation"),
        (re.compile(r"There were undefined references"), "latex_log_undefined_reference"),
        (re.compile(r"Undefined control sequence"), "latex_log_undefined_control_sequence"),
    ]
    for regex, rule in patterns:
        for match in regex.findall(text):
            match_text = match if isinstance(match, str) else str(match)
            add_issue(
                issues,
                allow_entries,
                severity,
                rule,
                log_rel,
                "Problem reported by LaTeX build log.",
                match_text,
            )


def scan_generated_files(
    root: Path,
    rules: dict[str, Any],
    allow_entries: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    aux_exts = set(rules.get("scan", {}).get("latex_aux_extensions", []))
    warning_bytes = int(float(rules.get("scan", {}).get("large_file_warning_mb", 20)) * 1024 * 1024)
    error_bytes = int(float(rules.get("scan", {}).get("large_file_error_mb", 100)) * 1024 * 1024)
    output_dirs = [root / item for item in rules.get("scan", {}).get("output_dirs", [])]

    for path in iter_files(root, rules):
        rel = relpath(root, path)
        lower = path.name.lower()
        if "__pycache__" in path.parts:
            add_issue(issues, allow_entries, "WARNING", "python_cache", rel, "Python cache file found.", rel)
        if any(lower.endswith(ext) for ext in aux_exts) and not rel.startswith("07_paper/build/"):
            add_issue(
                issues,
                allow_entries,
                "WARNING",
                "latex_aux_outside_build",
                rel,
                "LaTeX auxiliary file is outside 07_paper/build.",
                rel,
            )
        size = path.stat().st_size
        if size >= error_bytes:
            add_issue(issues, allow_entries, "ERROR", "large_file", rel, "File exceeds error size limit.", rel)
        elif size >= warning_bytes:
            add_issue(issues, allow_entries, "WARNING", "large_file", rel, "File exceeds warning size limit.", rel)
        if (
            size == 0
            and path.name != ".gitkeep"
            and any(path.is_relative_to(output_dir) for output_dir in output_dirs)
        ):
            add_issue(issues, allow_entries, "WARNING", "empty_output", rel, "Empty output file found.", rel)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_final_checksums(
    root: Path,
    rules: dict[str, Any],
    allow_entries: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    checksum_rel = rules.get("final", {}).get("checksums_file", "11_final_submission/checksums.sha256")
    checksum_path = root / checksum_rel
    if not checksum_path.exists():
        add_issue(issues, allow_entries, "ERROR", "final_checksum_file_missing", checksum_rel, "Checksum file is missing.", checksum_rel)
        return
    verified = 0
    for line_no, line in enumerate(checksum_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Fa-f0-9]{64})\s+\*?(.+)$", line)
        if not match:
            add_issue(
                issues,
                allow_entries,
                "ERROR",
                "final_checksum_format",
                checksum_rel,
                f"Invalid checksum line format at line {line_no}.",
                line,
            )
            continue
        expected, file_rel = match.groups()
        file_rel = file_rel.strip().replace("\\", "/")
        target = root / file_rel
        if not target.exists():
            add_issue(issues, allow_entries, "ERROR", "final_checksum_target_missing", checksum_rel, "Checksummed file is missing.", file_rel)
            continue
        actual = sha256_file(target)
        verified += 1
        if actual.lower() != expected.lower():
            add_issue(issues, allow_entries, "ERROR", "final_checksum_mismatch", file_rel, "SHA256 checksum mismatch.", expected)
    if verified == 0:
        add_issue(issues, allow_entries, "ERROR", "final_checksum_empty", checksum_rel, "No checksum entries were verified.", checksum_rel)


def count_pdf_pages(path: Path) -> int:
    data = path.read_bytes()
    return len(re.findall(rb"/Type\s*/Page\b", data))


def check_pdf_limits(
    root: Path,
    rules: dict[str, Any],
    allow_entries: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    final_cfg = rules.get("final", {})
    pdf_rel = final_cfg.get("final_pdf", "11_final_submission/final_paper.pdf")
    pdf_path = root / pdf_rel
    max_size_mb = final_cfg.get("max_pdf_size_mb")
    max_pages = final_cfg.get("max_pdf_pages")
    if max_size_mb is None and max_pages is None:
        add_issue(
            issues,
            allow_entries,
            "INFO",
            "official_limits_unset",
            "10_submission_check/submission_rules.yml",
            "PDF page and size limits are unset and must be reviewed against official 2026 rules.",
        )
        return
    if not pdf_path.exists():
        return
    if max_size_mb is not None and pdf_path.stat().st_size > float(max_size_mb) * 1024 * 1024:
        add_issue(issues, allow_entries, "ERROR", "pdf_size_limit", pdf_rel, "Final PDF exceeds configured size limit.", str(max_size_mb))
    if max_pages is not None:
        pages = count_pdf_pages(pdf_path)
        if pages > int(max_pages):
            add_issue(issues, allow_entries, "ERROR", "pdf_page_limit", pdf_rel, "Final PDF exceeds configured page limit.", str(max_pages))


def check_local_rules(
    rules: dict[str, Any],
    allow_entries: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    local_rules = rules.get("local_rules", {})
    if not isinstance(local_rules, dict):
        return
    for key, value in local_rules.items():
        if value is None:
            add_issue(
                issues,
                allow_entries,
                "INFO",
                "local_rule_unconfirmed",
                "10_submission_check/submission_rules.yml",
                "School or regional additional rule is still unconfirmed.",
                str(key),
            )


def check_official_rule_source(
    rules: dict[str, Any],
    allow_entries: list[dict[str, Any]],
    issues: list[Issue],
    mode: str,
) -> None:
    source = rules.get("official_rule_source", {})
    confirmed = (
        source.get("status") == "confirmed"
        and bool(source.get("asset_id"))
        and bool(re.fullmatch(r"[a-fA-F0-9]{64}", str(source.get("sha256", ""))))
        and bool(source.get("retrieved_at"))
    )
    if confirmed:
        return
    add_issue(
        issues,
        allow_entries,
        "ERROR" if mode == "final" else "WARNING",
        "official_rules_pending",
        "10_submission_check/submission_rules.yml",
        "National rule parameters require a local official source snapshot, SHA256, and retrieval time.",
        str(source.get("status", "missing")),
    )


def _add_gate_issues(
    gate_issues: Iterable[Any],
    allow_entries: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    for gate in gate_issues:
        details = getattr(gate, "details", {}) or {}
        match = str(
            details.get("assumption_id")
            or details.get("claim_id")
            or details.get("evidence_id")
            or details.get("figure_id")
            or ""
        )
        add_issue(
            issues,
            allow_entries,
            gate.severity,
            gate.rule,
            gate.path or "model_trust",
            gate.message,
            match,
        )


def check_model_trust(
    root: Path,
    rules: dict[str, Any],
    allow_entries: list[dict[str, Any]],
    issues: list[Issue],
    mode: str,
) -> None:
    config = rules.get("model_trust")
    if not isinstance(config, dict):
        return
    profile = "final" if mode == "final" else "audit"
    try:
        from quality_gates import assumption_gate_issues, validate_assumptions_registry
        from reporting.generate_claim_evidence_map import validate_evidence_tables
        from reporting.validate_figure_manifest import validate_figure_manifest

        assumptions_rel = config.get("assumptions_registry")
        if assumptions_rel:
            assumptions_path = root / assumptions_rel
            if not assumptions_path.is_file():
                add_issue(
                    issues,
                    allow_entries,
                    "ERROR" if mode == "final" else "WARNING",
                    "assumptions_registry_missing",
                    assumptions_rel,
                    "Assumption risk registry is missing.",
                    assumptions_rel,
                )
            else:
                registry = load_yaml(assumptions_path)
                validate_assumptions_registry(registry)
                _add_gate_issues(assumption_gate_issues(registry, profile), allow_entries, issues)

        claims_rel = config.get("claims")
        links_rel = config.get("evidence_links")
        if claims_rel and links_rel:
            evidence_report = validate_evidence_tables(
                root,
                root / claims_rel,
                root / links_rel,
                profile=profile,
            )
            _add_gate_issues(evidence_report.issues, allow_entries, issues)

        figure_rel = config.get("figure_manifest")
        if figure_rel:
            figure_report = validate_figure_manifest(root, profile=profile, write_metadata=False)
            _add_gate_issues(figure_report.issues, allow_entries, issues)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ConfigError(f"Invalid model-trust configuration: {exc}") from exc

    source_run_file_rel = config.get("final_source_run_id_file")
    if mode != "final" or not source_run_file_rel:
        return
    source_run_file = root / source_run_file_rel
    if not source_run_file.is_file():
        add_issue(
            issues,
            allow_entries,
            "ERROR",
            "final_source_run_missing",
            source_run_file_rel,
            "Final submission has no registered source_run_id.",
            source_run_file_rel,
        )
        return
    source_run_id = source_run_file.read_text(encoding="utf-8").strip()
    if not source_run_id or any(char in source_run_id for char in "/\\"):
        add_issue(
            issues,
            allow_entries,
            "ERROR",
            "final_source_run_invalid",
            source_run_file_rel,
            "source_run_id is empty or invalid.",
            source_run_id,
        )
        return
    run_dir = root / "05_model_results" / "runs" / source_run_id
    stage_path = run_dir / "stage_report.json"
    manifest_path = run_dir / "run_manifest.json"
    if not stage_path.is_file() or not manifest_path.is_file():
        add_issue(
            issues,
            allow_entries,
            "ERROR",
            "final_source_run_artifacts_missing",
            source_run_file_rel,
            "The registered source run lacks its manifest or stage report.",
            source_run_id,
        )
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        stage_report = json.loads(stage_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid source-run JSON: {exc}") from exc
    if manifest.get("status") != "completed":
        add_issue(
            issues,
            allow_entries,
            "ERROR",
            "final_source_run_incomplete",
            relpath(root, manifest_path),
            "The registered source run is not completed.",
            source_run_id,
        )
    if config.get("require_cold_reproduction_in_final", True):
        cold = [
            stage
            for stage in stage_report.get("stages", [])
            if stage.get("name") == "cold_reproduction"
        ]
        if not cold or cold[-1].get("status") != "completed":
            add_issue(
                issues,
                allow_entries,
                "ERROR",
                "cold_reproduction_missing_or_failed",
                relpath(root, stage_path),
                "Final source run did not complete cold reproduction.",
                source_run_id,
            )


def run_checks(
    root: Path,
    mode: str,
    rules_path: Path,
    sensitive_path: Path,
    allowlist_path: Path,
) -> list[Issue]:
    root = root.resolve()
    rules = load_yaml(rules_path)
    allowlist = load_yaml(allowlist_path)
    allow_entries = list(allowlist.get("allow", []) or [])
    issues: list[Issue] = []
    sensitive = load_sensitive_config(root, sensitive_path, mode, allow_entries, issues)

    check_required_files(root, rules, allow_entries, issues, mode)
    scan_sensitive_terms(root, rules, sensitive, allow_entries, issues, mode)
    scan_text_patterns(root, rules, allow_entries, issues, mode)
    scan_latex_sources(root, rules, allow_entries, issues)
    scan_latex_log(root, rules, allow_entries, issues, mode)
    scan_generated_files(root, rules, allow_entries, issues)
    check_pdf_limits(root, rules, allow_entries, issues)
    check_official_rule_source(rules, allow_entries, issues, mode)
    check_local_rules(rules, allow_entries, issues)
    check_model_trust(root, rules, allow_entries, issues, mode)
    if mode == "final":
        verify_final_checksums(root, rules, allow_entries, issues)
    return sorted(issues, key=lambda item: (SEVERITIES.index(item.severity), item.rule, item.path, item.match))


def print_report(issues: list[Issue], mode: str) -> None:
    counts = {severity: 0 for severity in SEVERITIES}
    for issue in issues:
        counts[issue.severity] += 1
    console_print(f"CUMCM2026 submission check mode={mode}")
    console_print("NOTICE: Automated checks cannot replace manual compliance review by the team.")
    console_print(f"Summary: ERROR={counts['ERROR']} WARNING={counts['WARNING']} INFO={counts['INFO']}")
    for issue in issues:
        match = f" match={issue.match!r}" if issue.match else ""
        console_print(f"[{issue.severity}] {issue.rule} {issue.path}: {issue.message}{match}")


def console_text(value: str, encoding: str | None) -> str:
    resolved = encoding or "utf-8"
    return value.encode(resolved, errors="backslashreplace").decode(resolved)


def console_print(value: str, *, stream: Any = None) -> None:
    target = stream or sys.stdout
    print(console_text(value, getattr(target, "encoding", None)), file=target)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Workspace root, default: current directory.")
    parser.add_argument("--mode", choices=("draft", "final"), default="draft")
    parser.add_argument("--rules", default="10_submission_check/submission_rules.yml")
    parser.add_argument("--sensitive-terms", default="10_submission_check/sensitive_terms.local.yml")
    parser.add_argument("--allowlist", default="10_submission_check/allowlist.yml")
    parser.add_argument("--json", dest="json_path", default=None, help="Optional JSON report path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = Path(args.root).resolve()
    try:
        issues = run_checks(
            root=root,
            mode=args.mode,
            rules_path=root / args.rules,
            sensitive_path=root / args.sensitive_terms,
            allowlist_path=root / args.allowlist,
        )
        if args.json_path:
            output = root / args.json_path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps([asdict(issue) for issue in issues], ensure_ascii=False, indent=2), encoding="utf-8")
        print_report(issues, args.mode)
        return 1 if any(issue.severity == "ERROR" for issue in issues) else 0
    except ConfigError as exc:
        console_print(f"[CONFIG ERROR] {exc}", stream=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        console_print(f"[SCRIPT ERROR] {type(exc).__name__}: {exc}", stream=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
