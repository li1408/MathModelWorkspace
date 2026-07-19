"""Preview or apply explicit project configuration migrations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from workflow_core.config.migrations import migrate_project_config
from workflow_core.quality.gates import EXIT_OK, EXIT_SYSTEM_ERROR


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--to-version", required=True, type=int)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = migrate_project_config(
            Path(args.project).resolve(),
            args.to_version,
            apply=bool(args.apply),
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001
        print(f"Configuration migration failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_SYSTEM_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
