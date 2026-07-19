"""Resolve logical asset URIs through a Git-ignored local mapping."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from workflow_core.config.loader import load_yaml


LOGICAL_URI = re.compile(r"^(asset://(?:raw|template|reference)/[a-z0-9][a-z0-9._-]*|run://[A-Za-z0-9._-]+/[A-Za-z0-9._-]+)$")


class AssetResolutionError(ValueError):
    """Raised when a logical asset cannot be resolved or verified."""


@dataclass(frozen=True)
class ResolvedAsset:
    asset_id: str
    logical_uri: str
    local_path: Path
    sha256: str
    size_bytes: int
    read_only: bool


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class AssetResolver:
    def __init__(self, project_root: Path, local_map_path: Path) -> None:
        self.project_root = project_root.resolve()
        local_map = load_yaml(local_map_path)
        self.mapping = local_map.get("assets", {})
        if not isinstance(self.mapping, dict):
            raise AssetResolutionError("Local asset mapping must contain an assets mapping.")

    def resolve(self, asset: dict[str, Any]) -> ResolvedAsset:
        asset_id = str(asset.get("asset_id", ""))
        logical_uri = str(asset.get("logical_uri", ""))
        if not asset_id or not LOGICAL_URI.fullmatch(logical_uri):
            raise AssetResolutionError(f"Invalid asset_id or logical_uri: {asset_id}, {logical_uri}")
        local_entry = self.mapping.get(logical_uri)
        if not isinstance(local_entry, dict) or not local_entry.get("path"):
            raise AssetResolutionError(f"No local mapping for {logical_uri}")
        path = Path(str(local_entry["path"])).expanduser()
        if not path.is_absolute():
            path = self.project_root / path
        path = path.resolve()
        if not path.is_file():
            raise AssetResolutionError(f"Mapped asset does not exist: {logical_uri}")
        actual_hash = sha256_file(path)
        expected_hash = str(asset.get("sha256", ""))
        if expected_hash and actual_hash.lower() != expected_hash.lower():
            raise AssetResolutionError(f"SHA256 mismatch for {logical_uri}")
        expected_size = asset.get("size_bytes")
        if expected_size is not None and path.stat().st_size != int(expected_size):
            raise AssetResolutionError(f"File size mismatch for {logical_uri}")
        return ResolvedAsset(
            asset_id=asset_id,
            logical_uri=logical_uri,
            local_path=path,
            sha256=actual_hash,
            size_bytes=path.stat().st_size,
            read_only=bool(asset.get("read_only", True)),
        )
