"""Dispatch read-only audits from confirmed logical data types."""

from __future__ import annotations

from typing import Any, Iterable

from workflow_core.assets.resolver import ResolvedAsset
from workflow_core.sdk import GateReport

from .tabular import audit_tabular
from .network import audit_network_workbook


def audit_assets(
    assets: Iterable[ResolvedAsset],
    catalog_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], GateReport]:
    report = GateReport(stage="data_audit")
    summaries: list[dict[str, Any]] = []
    for asset in assets:
        catalog = catalog_by_id.get(asset.asset_id, {})
        logical_type = catalog.get("confirmed_type") or catalog.get("logical_type")
        summary: dict[str, Any] = {
            "asset_id": asset.asset_id,
            "logical_uri": asset.logical_uri,
            "sha256": asset.sha256,
            "size_bytes": asset.size_bytes,
            "logical_type": logical_type,
        }
        try:
            if logical_type in {"tabular", "network"}:
                summary["tabular"] = audit_tabular(asset.local_path)
                if logical_type == "network":
                    mapping = (
                        catalog.get("extensions", {})
                        .get("network_routing", {})
                        .get("data_asset")
                    )
                    if not isinstance(mapping, dict):
                        raise ValueError(
                            "Network assets require extensions.network_routing column mapping."
                        )
                    summary["network"] = audit_network_workbook(asset.local_path, mapping)
            else:
                report.add(
                    "INFO",
                    "data_audit_type_not_implemented",
                    "Only generic file integrity checks were run for this data type.",
                    match=str(logical_type),
                )
        except Exception as exc:  # noqa: BLE001
            report.add(
                "ERROR",
                "data_audit_read_failure",
                f"Cannot audit asset: {type(exc).__name__}: {exc}",
                match=asset.asset_id,
            )
        summaries.append(summary)
    report.metrics = {"asset_count": len(summaries)}
    return {"schema_version": 1, "assets": summaries}, report
