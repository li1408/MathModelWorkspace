"""Validate generic network-routing extension data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--response", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    extension = request.get("extension", {})
    issues = [] if isinstance(extension, dict) else ["extension must be an object"]
    response = {"status": "VALID" if not issues else "INVALID", "issues": issues}
    Path(args.response).write_text(json.dumps(response, indent=2) + "\n", encoding="utf-8")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
