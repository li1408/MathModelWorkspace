"""Run the compatible baseline pipeline or an isolated trust-workflow profile."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from quality_gates import assumption_gate_issues
from run_context import RunContext


CODE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_DIR.parent

LEGACY_PIPELINE = [
    "01_data_check.py",
    "02_data_cleaning.py",
    "03_exploratory_analysis.py",
    "04_model_q1.py",
    "05_model_q2.py",
    "06_model_q3.py",
    "07_model_q4.py",
    "07_model_validation.py",
    "08_sensitivity_analysis.py",
    "09_generate_figures.py",
    "10_export_results.py",
]

# Kept as an alias for existing imports and documentation.
PIPELINE = LEGACY_PIPELINE

STAGE_ORDER = [
    "data_check",
    "preprocessing",
    "baseline",
    "alternatives",
    "invariants",
    "algorithm_preconditions",
    "convergence",
    "parameter_sensitivity",
    "structural_sensitivity",
    "comparison_audit",
    "figures",
    "evidence_map",
    "paper_exports",
    "supporting_materials",
    "cold_reproduction",
    "submission_check",
]

PROFILE_STAGES = {
    "practice": [
        "data_check",
        "preprocessing",
        "baseline",
        "invariants",
        "parameter_sensitivity",
        "figures",
        "paper_exports",
        "supporting_materials",
        "submission_check",
    ],
    "audit": [stage for stage in STAGE_ORDER if stage != "cold_reproduction"],
    "final": list(STAGE_ORDER),
}

STAGE_ALIASES = {"fifo": "algorithm_preconditions"}

STAGE_SCRIPTS = {
    "data_check": ["01_data_check.py"],
    "preprocessing": ["02_data_cleaning.py", "03_exploratory_analysis.py"],
    "baseline": ["04_model_q1.py", "05_model_q2.py", "06_model_q3.py", "07_model_q4.py"],
    "alternatives": ["validation/compare_model_structures.py", "--mode", "alternatives"],
    "invariants": ["07_model_validation.py"],
    "algorithm_preconditions": ["validation/test_fifo.py"],
    "convergence": ["validation/test_convergence.py"],
    "parameter_sensitivity": ["08_sensitivity_analysis.py"],
    "structural_sensitivity": ["validation/compare_model_structures.py", "--mode", "structural"],
    "comparison_audit": ["validation/comparison_audit.py"],
    "figures": ["09_generate_figures.py"],
    "evidence_map": ["reporting/generate_claim_evidence_map.py"],
    "supporting_materials": ["10_export_results.py"],
    "cold_reproduction": ["validation/validate_cold_reproduction.py"],
}


def normalize_stage(value: str) -> str:
    normalized = STAGE_ALIASES.get(value.strip(), value.strip())
    if normalized not in STAGE_ORDER:
        raise ValueError(f"Unknown stage: {value}")
    return normalized


def resolve_stage_selection(
    profile: str,
    *,
    stage: str | None,
    from_stage: str | None,
    stages: str | None,
) -> list[str]:
    selectors = [value is not None for value in (stage, from_stage, stages)]
    if sum(selectors) > 1:
        raise ValueError("Use only one of --stage, --from-stage, or --stages.")
    if stage is not None:
        return [normalize_stage(stage)]
    if from_stage is not None:
        start_stage = normalize_stage(from_stage)
        profile_stages = PROFILE_STAGES[profile]
        if start_stage not in profile_stages:
            raise ValueError(f"Stage {start_stage} is not part of profile {profile}.")
        return profile_stages[profile_stages.index(start_stage) :]
    if stages is not None:
        selected = [normalize_stage(item) for item in stages.split(",") if item.strip()]
        if not selected:
            raise ValueError("--stages must contain at least one stage.")
        if len(selected) != len(set(selected)):
            raise ValueError("--stages must not contain duplicate stages.")
        return selected
    return list(PROFILE_STAGES[profile])


def run_step(script_name: str, *, env: dict[str, str] | None = None, extra_args: list[str] | None = None) -> None:
    script_path = CODE_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"Pipeline script does not exist: {script_path}")
    subprocess.run(
        [sys.executable, str(script_path), *(extra_args or [])],
        cwd=CODE_DIR,
        env=env,
        check=True,
    )


def run_legacy_pipeline(*, dry_run: bool) -> int:
    for index, script_name in enumerate(LEGACY_PIPELINE, start=1):
        if dry_run:
            print(f"{index:02d}. {script_name}")
        else:
            print(f"[{index}/{len(LEGACY_PIPELINE)}] Running {script_name}")
            run_step(script_name)
    return 0


def run_paper_exports(env: dict[str, str]) -> None:
    wrapper = PROJECT_ROOT / ".local" / "bin" / "latexmk.cmd"
    if not wrapper.exists():
        raise FileNotFoundError(f"Project-local latexmk wrapper is missing: {wrapper}")
    subprocess.run(
        [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(wrapper), "-xelatex", "-outdir=build", "main.tex"],
        cwd=PROJECT_ROOT / "07_paper",
        env=env,
        check=True,
    )


def run_submission_check(context: RunContext, env: dict[str, str]) -> None:
    profile = context.profile
    mode = "final" if profile == "final" else "draft"
    json_rel = (context.run_dir / "logs" / "submission_check.json").relative_to(
        PROJECT_ROOT
    ).as_posix()
    subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "10_submission_check" / "check_submission.py"),
            "--root",
            str(PROJECT_ROOT),
            "--mode",
            mode,
            "--json",
            json_rel,
        ],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
    )


def collect_stage_issues(context: RunContext, stage: str) -> list[dict[str, object]]:
    if stage == "baseline":
        registry = yaml.safe_load(
            (PROJECT_ROOT / "04_code/config/assumptions_registry.yml").read_text(
                encoding="utf-8"
            )
        )
        return [issue.to_dict() for issue in assumption_gate_issues(registry, context.profile)]
    report_paths = {
        "alternatives": context.run_dir / "alternatives/strategy_status.json",
        "algorithm_preconditions": context.run_dir / "fifo/fifo_report.json",
        "convergence": context.run_dir / "convergence/convergence_report.json",
        "structural_sensitivity": context.run_dir / "comparisons/structural_sensitivity.json",
        "comparison_audit": context.run_dir / "comparisons/comparison_audit.json",
        "figures": context.run_dir / "figures/figure_quality_report.json",
        "evidence_map": context.run_dir / "evidence/evidence_map_report.json",
        "cold_reproduction": context.run_dir / "cold_reproduction/cold_reproduction_report.json",
        "submission_check": context.run_dir / "logs/submission_check.json",
    }
    path = report_paths.get(stage)
    if path is None or not path.is_file():
        return []
    loaded = json.loads(path.read_text(encoding="utf-8"))
    raw_issues = loaded if isinstance(loaded, list) else loaded.get("issues", [])
    normalized: list[dict[str, object]] = []
    for issue in raw_issues:
        if not isinstance(issue, dict):
            continue
        normalized.append(
            {
                "severity": issue.get("severity", "INFO"),
                "rule": issue.get("rule", "stage_issue"),
                "message": issue.get("message", ""),
                "path": issue.get("path", ""),
                "details": issue.get("details", {"match": issue.get("match", "")}),
            }
        )
    return normalized


def collect_stage_outputs(context: RunContext, stage: str) -> list[str]:
    directory_names = {
        "alternatives": ("alternatives",),
        "algorithm_preconditions": ("fifo",),
        "convergence": ("convergence",),
        "structural_sensitivity": ("comparisons",),
        "comparison_audit": ("comparisons",),
        "figures": ("figures",),
        "evidence_map": ("evidence",),
        "cold_reproduction": ("cold_reproduction",),
        "submission_check": ("logs",),
    }
    outputs = context.capture_compatibility_outputs(stage)
    for name in directory_names.get(stage, ()):
        directory = context.run_dir / name
        outputs.extend(
            path.relative_to(context.run_dir).as_posix()
            for path in directory.rglob("*")
            if path.is_file()
        )
    return sorted(set(outputs))


def run_extended_stage(context: RunContext, stage: str) -> tuple[list[str], list[dict[str, object]]]:
    env = context.environment_for_subprocess()
    if stage == "paper_exports":
        run_paper_exports(env)
    elif stage == "submission_check":
        run_submission_check(context, env)
    else:
        command = STAGE_SCRIPTS.get(stage)
        if command is None:
            raise RuntimeError(f"No implementation is registered for stage: {stage}")
        run_step(command[0], env=env, extra_args=command[1:])
    return collect_stage_outputs(context, stage), collect_stage_issues(context, stage)


def run_extended_pipeline(profile: str, stages: list[str], run_id: str | None) -> int:
    if run_id is None:
        context = RunContext.create(PROJECT_ROOT, profile, stages)
    else:
        context = RunContext.load(PROJECT_ROOT, run_id)
        context.mark_running_stages_interrupted()
        if context.profile != profile:
            raise ValueError(
                f"Run {run_id} uses profile {context.profile}, not requested profile {profile}."
            )
        context.manifest["requested_stages"] = stages
        context.requested_stages = stages

    print(f"run_id={context.run_id}")
    print(f"run_dir={context.run_dir.relative_to(PROJECT_ROOT).as_posix()}")
    try:
        for index, stage in enumerate(stages, start=1):
            print(f"[{index}/{len(stages)}] Stage {stage}")
            context.start_stage(stage)
            try:
                outputs, issues = run_extended_stage(context, stage)
            except subprocess.CalledProcessError as exc:
                outputs = collect_stage_outputs(context, stage)
                issues = collect_stage_issues(context, stage)
                if not issues:
                    issues = [
                        {
                            "severity": "ERROR",
                            "rule": "stage_command_failed",
                            "message": f"Stage command returned exit code {exc.returncode}.",
                        }
                    ]
                context.finish_stage(stage, status="failed", outputs=outputs, issues=issues)
                raise
            except Exception as exc:
                context.finish_stage(
                    stage,
                    status="failed",
                    issues=[{"severity": "ERROR", "message": f"{type(exc).__name__}: {exc}"}],
                )
                raise
            if any(issue.get("severity") == "ERROR" for issue in issues):
                context.finish_stage(stage, status="failed", outputs=outputs, issues=issues)
                context.finalize("failed")
                print(f"Stage quality gate failed: {stage}", file=sys.stderr)
                return 1
            context.finish_stage(stage, status="completed", outputs=outputs, issues=issues)
        context.finalize("completed")
        return 0
    except subprocess.CalledProcessError as exc:
        context.finalize("failed")
        print(f"Stage command failed with exit code {exc.returncode}.", file=sys.stderr)
        return 2 if exc.returncode == 2 else 1
    except Exception as exc:  # noqa: BLE001
        context.finalize("failed")
        print(f"Workflow failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print the selected execution order only.")
    parser.add_argument("--profile", choices=tuple(PROFILE_STAGES), default=None)
    parser.add_argument("--stage", default=None, help="Run one stage only.")
    parser.add_argument("--from-stage", default=None, help="Run from this stage to the profile end.")
    parser.add_argument("--stages", default=None, help="Run an explicit comma-separated stage list.")
    parser.add_argument("--run-id", default=None, help="Resume an existing isolated run.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    has_extended_options = any(
        value is not None for value in (args.profile, args.stage, args.from_stage, args.stages, args.run_id)
    )
    if not has_extended_options:
        return run_legacy_pipeline(dry_run=args.dry_run)

    profile = args.profile or ("audit" if any((args.stage, args.from_stage, args.stages)) else "practice")
    try:
        selected = resolve_stage_selection(
            profile,
            stage=args.stage,
            from_stage=args.from_stage,
            stages=args.stages,
        )
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        for index, stage in enumerate(selected, start=1):
            print(f"{index:02d}. {stage}")
        return 0
    return run_extended_pipeline(profile, selected, args.run_id)


if __name__ == "__main__":
    raise SystemExit(main())
