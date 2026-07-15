from __future__ import annotations

import csv
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from .config import RegistryConfig
from .db import RegistryDB
from .forecast_performance import build_forecast_performance


RECORD_FIELDS = [
    "record_id",
    "variable_id",
    "variable_name",
    "class_name",
    "source_id",
    "source_name",
    "publisher",
    "source_url",
    "source_series_id",
    "value",
    "range_low",
    "range_high",
    "unit_original",
    "unit_canonical",
    "record_kind",
    "geography_id",
    "entity_id",
    "reference_period_start",
    "reference_period_end",
    "target_period_start",
    "target_period_end",
    "period_basis",
    "publication_date",
    "vintage_date",
    "scenario_original",
    "scenario_family",
    "statistic_type",
    "currency",
    "price_base_year",
    "real_or_nominal",
    "document_id",
    "document_url",
    "document_sha256",
    "document_retrieved_at",
    "evidence_page",
    "evidence_table",
    "evidence_text",
    "extraction_method",
    "validation_status",
    "quality_flags",
    "evidence_type",
    "assumption_owner",
    "source_status",
    "decision_context",
    "approval_status",
    "parameter_scope",
    "time_basis",
    "metadata",
    "first_seen_at",
    "last_seen_at",
    "valid_from",
    "valid_to",
    "is_current",
    "supersedes_record_id",
]

DOCUMENT_FIELDS = [
    "document_id",
    "source_id",
    "source_url",
    "local_path",
    "content_type",
    "retrieved_at",
    "sha256",
    "size_bytes",
    "request_method",
    "request_metadata",
    "response_headers",
]

RUN_FIELDS = [
    "run_id",
    "source_id",
    "started_at",
    "finished_at",
    "status",
    "records_seen",
    "records_inserted",
    "records_revised",
    "records_unchanged",
    "records_rejected",
    "warnings",
    "error",
]


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fieldnames: list[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(fieldnames or [])
    seen = set(fields)
    for row in rows:
        for key in row:
            if key not in seen:
                fields.append(key)
                seen.add(key)
    temporary = path.with_name(f".{path.name}.tmp")
    if not fields:
        temporary.write_text("", encoding="utf-8")
        temporary.replace(path)
        return
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (
                        json.dumps(value, ensure_ascii=False, sort_keys=True)
                        if isinstance(value, (dict, list))
                        else value
                    )
                    for key, value in row.items()
                }
            )
    temporary.replace(path)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def _decode_json(value: Any, fallback: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _is_public_record(row: dict[str, Any], config: RegistryConfig) -> bool:
    source = config.sources.get(row["source_id"], {})
    publication = config.validation.get("publication", {})
    allowed_statuses = set(publication.get("allowed_statuses", ["validated", "approved"]))
    excluded_kinds = set(publication.get("exclude_record_kinds", []))
    return bool(
        source.get("publish_enabled", False)
        and row.get("validation_status") in allowed_statuses
        and row.get("record_kind") not in excluded_kinds
    )


def _record_export(row: dict[str, Any]) -> dict[str, Any]:
    metadata = _decode_json(row.get("metadata_json"), {})
    return {
        "record_id": row["record_id"],
        "variable_id": row["variable_id"],
        "variable_name": row["variable_name"],
        "class_name": row["class_name"],
        "source_id": row["source_id"],
        "source_name": row["source_name"],
        "publisher": row["publisher"],
        "source_url": row.get("source_url"),
        "source_series_id": row["source_series_id"],
        "value": row["value"],
        "range_low": row["range_low"],
        "range_high": row["range_high"],
        "unit_original": row["unit_original"],
        "unit_canonical": row["unit_canonical"],
        "record_kind": row["record_kind"],
        "geography_id": row["geography_id"],
        "entity_id": row["entity_id"],
        "reference_period_start": row["reference_period_start"],
        "reference_period_end": row["reference_period_end"],
        "target_period_start": row["target_period_start"],
        "target_period_end": row["target_period_end"],
        "period_basis": row["period_basis"],
        "publication_date": row["publication_date"],
        "vintage_date": row["vintage_date"],
        "scenario_original": row["scenario_original"],
        "scenario_family": row["scenario_family"],
        "statistic_type": row["statistic_type"],
        "currency": row["currency"],
        "price_base_year": row["price_base_year"],
        "real_or_nominal": row["real_or_nominal"],
        "document_id": row["document_id"],
        "document_url": row.get("document_url"),
        "document_sha256": row.get("document_sha256"),
        "document_retrieved_at": row.get("document_retrieved_at"),
        "evidence_page": row["evidence_page"],
        "evidence_table": row["evidence_table"],
        "evidence_text": row["evidence_text"],
        "extraction_method": row["extraction_method"],
        "validation_status": row["validation_status"],
        "quality_flags": _decode_json(row.get("quality_flags_json"), []),
        "evidence_type": metadata.get("evidence_type"),
        "assumption_owner": metadata.get("assumption_owner"),
        "source_status": metadata.get("source_status"),
        "decision_context": metadata.get("decision_context"),
        "approval_status": metadata.get("approval_status"),
        "parameter_scope": metadata.get("parameter_scope"),
        "time_basis": metadata.get("time_basis"),
        "metadata": metadata,
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "valid_from": row["valid_from"],
        "valid_to": row["valid_to"],
        "is_current": bool(row["is_current"]),
        "supersedes_record_id": row["supersedes_record_id"],
    }


def _variable_export(variable_id: str, variable: dict[str, Any]) -> dict[str, Any]:
    return {
        "variable_id": variable_id,
        "class_name": variable["class"],
        "name": variable["name"],
        "description": variable.get("description"),
        "canonical_unit": variable["canonical_unit"],
        "geography_id": variable.get("geography_id"),
        "status": variable.get("status"),
        "phase": variable.get("phase"),
        "expected_min": variable.get("expected_min"),
        "expected_max": variable.get("expected_max"),
        "temporal_semantics": variable.get("temporal_semantics"),
        "required_metadata": variable.get("required_metadata", []),
    }


def _run_export(row: dict[str, Any]) -> dict[str, Any]:
    clean = {key: value for key, value in row.items() if key != "warnings_json"}
    clean["warnings"] = _decode_json(row.get("warnings_json"), [])
    return clean


def _source_run_export(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "run_id": row.get("run_id"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "status": row.get("status"),
        "records_seen": row.get("records_seen"),
        "records_inserted": row.get("records_inserted"),
        "records_revised": row.get("records_revised"),
        "records_unchanged": row.get("records_unchanged"),
        "records_rejected": row.get("records_rejected"),
    }


def export_registry(
    config: RegistryConfig,
    db: RegistryDB | None = None,
) -> dict[str, Any]:
    registry = db or RegistryDB(config.paths.db)
    registry.initialize()
    registry.sync_config(config.variables, config.sources)

    current_rows = registry.current_records(publishable_only=False)
    history_rows = registry.history_records()
    public_current = [_record_export(row) for row in current_rows if _is_public_record(row, config)]
    public_history = [_record_export(row) for row in history_rows if _is_public_record(row, config)]

    all_runs = [_run_export(row) for row in registry.table_rows("runs")]
    public_source_ids = {
        source_id
        for source_id, source in config.sources.items()
        if source.get("publish_enabled", False)
    }
    public_runs = [row for row in all_runs if row["source_id"] in public_source_ids]

    public_document_ids = {
        row["document_id"] for row in [*public_current, *public_history] if row.get("document_id")
    }
    public_documents = []
    for row in registry.table_rows("documents"):
        if row["source_id"] not in public_source_ids:
            continue
        if row["document_id"] not in public_document_ids:
            continue
        clean = {
            key: value
            for key, value in row.items()
            if key not in {"request_metadata_json", "response_headers_json"}
        }
        clean["request_metadata"] = _decode_json(row.get("request_metadata_json"), {})
        clean["response_headers"] = _decode_json(row.get("response_headers_json"), {})
        public_documents.append(clean)

    variables = [
        _variable_export(variable_id, variable)
        for variable_id, variable in sorted(config.variables.items())
    ]
    forecast_performance = build_forecast_performance(
        public_current,
        source_authority={
            source_id: int(source.get("authority_tier", 99))
            for source_id, source in config.sources.items()
        },
    )

    latest_run_by_source: dict[str, dict[str, Any]] = {}
    for run in all_runs:
        existing = latest_run_by_source.get(run["source_id"])
        if existing is None or run["started_at"] > existing["started_at"]:
            latest_run_by_source[run["source_id"]] = run

    sources = []
    for source_id, source in sorted(config.sources.items()):
        sources.append(
            {
                "source_id": source_id,
                "name": source["name"],
                "publisher": source["publisher"],
                "authority_tier": source.get("authority_tier"),
                "adapter": source["adapter"],
                "enabled": bool(source.get("enabled", False)),
                "publish_enabled": bool(source.get("publish_enabled", False)),
                "optional": bool(source.get("optional", False)),
                "required": bool(source.get("required", not source.get("optional", False))),
                "collection_stale_after_days": source.get("collection_stale_after_days"),
                "stale_after_days": source.get("stale_after_days"),
                "source_url": source.get("source_url"),
                "update_cadence": source.get("update_cadence"),
                "license_name": source.get("license_name"),
                "raw_redistribution_allowed": source.get("raw_redistribution_allowed"),
                "notes": source.get("notes"),
                "latest_run": _source_run_export(latest_run_by_source.get(source_id)),
            }
        )

    enabled_source_ids = {
        source_id for source_id, source in config.sources.items() if source.get("enabled", False)
    }
    successful_finished = [
        row["finished_at"]
        for row in all_runs
        if row.get("source_id") in enabled_source_ids
        and row.get("status") == "success"
        and row.get("finished_at")
    ]
    latest_successful_run = max(successful_finished) if successful_finished else None
    failed_sources = [
        {
            "source_id": source_id,
            "status": row["status"],
            "started_at": row["started_at"],
            "finished_at": row.get("finished_at"),
        }
        for source_id, row in sorted(latest_run_by_source.items())
        if source_id in enabled_source_ids and row.get("status") in {"failed", "partial"}
    ]

    summary = {
        "schema_version": "2.0.0-rc2",
        "generated_at": _utc_now(),
        "configured_variable_count": len(config.variables),
        "configured_source_count": len(config.sources),
        "enabled_source_count": sum(
            1 for source in config.sources.values() if source.get("enabled", False)
        ),
        "required_source_count": sum(
            1
            for source in config.sources.values()
            if source.get("enabled", False)
            and source.get("required", not source.get("optional", False))
        ),
        "current_record_count": len(public_current),
        "history_record_count": len(public_history),
        "variable_count": len({row["variable_id"] for row in public_current}),
        "source_count": len({row["source_id"] for row in public_current}),
        "document_count": len(public_documents),
        "forecast_performance_match_count": len(forecast_performance),
        "latest_successful_run": latest_successful_run,
        "failed_sources": failed_sources,
        "classes": sorted({row["class_name"] for row in variables}),
    }

    output = {
        "summary": summary,
        "records": public_current,
        "history": public_history,
        "variables": variables,
        "sources": sources,
        "runs": public_runs,
        "documents": public_documents,
        "forecast_performance": forecast_performance,
    }

    _write_csv(config.paths.export_dir / "records.csv", public_current, RECORD_FIELDS)
    _write_csv(config.paths.site_data_dir / "records.csv", public_current, RECORD_FIELDS)
    _write_json(config.paths.export_dir / "records.json", public_current)
    _write_csv(config.paths.export_dir / "records_history.csv", public_history, RECORD_FIELDS)
    _write_json(config.paths.export_dir / "records_history.json", public_history)
    _write_csv(config.paths.export_dir / "variables.csv", variables)
    _write_json(config.paths.export_dir / "variables.json", variables)
    _write_csv(config.paths.export_dir / "sources.csv", sources)
    _write_json(config.paths.export_dir / "sources.json", sources)
    _write_csv(config.paths.export_dir / "documents.csv", public_documents, DOCUMENT_FIELDS)
    _write_json(config.paths.export_dir / "documents.json", public_documents)
    _write_csv(config.paths.export_dir / "runs.csv", public_runs, RUN_FIELDS)
    _write_json(config.paths.export_dir / "runs.json", public_runs)
    _write_json(config.paths.export_dir / "summary.json", summary)
    _write_csv(config.paths.export_dir / "forecast_performance.csv", forecast_performance)
    _write_json(config.paths.export_dir / "forecast_performance.json", forecast_performance)

    site_output = {
        key: output[key]
        for key in (
            "summary", "records", "variables", "sources", "runs", "documents",
            "forecast_performance",
        )
    }
    for name in (
        "records", "variables", "sources", "runs", "summary", "forecast_performance"
    ):
        _write_json(config.paths.site_data_dir / f"{name}.json", site_output[name])
    _write_json(config.paths.site_data_dir / "registry.json", site_output)
    return output
