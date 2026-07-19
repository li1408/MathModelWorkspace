"""Launch trusted plugin or case modules without importing them into the core."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def run_module(
    *,
    repository_root: Path,
    module: str,
    request: dict[str, Any],
    request_path: Path,
    response_path: Path,
) -> dict[str, Any]:
    if not (module.startswith("plugins.") or module.startswith("cases.")):
        raise ValueError("Only trusted plugin and case modules may be launched.")
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    subprocess.run(
        [sys.executable, "-m", module, "--request", str(request_path), "--response", str(response_path)],
        cwd=repository_root,
        check=True,
    )
    if not response_path.is_file():
        raise RuntimeError(f"Trusted module did not produce its response: {module}")
    return json.loads(response_path.read_text(encoding="utf-8"))
