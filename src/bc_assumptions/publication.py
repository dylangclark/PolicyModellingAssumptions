from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import re
from typing import Any

from .config import RegistryConfig


class PublicationError(RuntimeError):
    pass


_SITE_JSON = {
    "summary": dict,
    "records": list,
    "variables": list,
    "sources": list,
    "runs": list,
    "registry": dict,
}

_SECRET_PATTERNS = [
    re.compile(
        r"(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret)="
        r"(?!REDACTED(?:&|$)|%5BREDACTED%5D(?:&|$))[^&\s\"']+"
    ),
    re.compile(r"(?i)authorization\s*[:=]\s*bearer\s+(?!REDACTED\b)[^\s\"']+"),
]


def _read_json(path: Path, expected_type: type) -> Any:
    if not path.exists():
        raise PublicationError(f"Missing public data file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, expected_type):
        raise PublicationError(f"Unexpected JSON type in {path}: expected {expected_type.__name__}")
    return value


def _csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise PublicationError(f"Missing public CSV file: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _assert_count(summary: dict[str, Any], key: str, actual: int, errors: list[str]) -> None:
    if summary.get(key) != actual:
        errors.append(f"summary.{key}={summary.get(key)!r}; expected {actual}")


def _scan_for_secrets(paths: list[Path], errors: list[str]) -> None:
    for path in paths:
        if not path.exists() or path.suffix.lower() not in {".json", ".csv"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in _SECRET_PATTERNS:
            match = pattern.search(text)
            if match:
                errors.append(f"Potential credential found in {path}: {match.group(0)[:80]!r}")
                break


def validate_publication(config: RegistryConfig) -> dict[str, int]:
    """Validate generated GitHub-facing artifacts without modifying them."""

    site: dict[str, Any] = {}
    for name, expected_type in _SITE_JSON.items():
        site[name] = _read_json(config.paths.site_data_dir / f"{name}.json", expected_type)

    summary = site["summary"]
    records = site["records"]
    variables = site["variables"]
    sources = site["sources"]
    runs = site["runs"]
    registry = site["registry"]
    documents = registry.get("documents")
    if not isinstance(documents, list):
        raise PublicationError("site/data/registry.json is missing a documents list")

    errors: list[str] = []
    for key in ("summary", "records", "variables", "sources", "runs", "documents"):
        if registry.get(key) != (documents if key == "documents" else site.get(key)):
            errors.append(f"registry.json section {key!r} does not match its canonical site data")

    _assert_count(summary, "current_record_count", len(records), errors)
    _assert_count(summary, "configured_variable_count", len(variables), errors)
    _assert_count(summary, "configured_source_count", len(sources), errors)
    _assert_count(
        summary, "variable_count", len({row.get("variable_id") for row in records}), errors
    )
    _assert_count(summary, "source_count", len({row.get("source_id") for row in records}), errors)
    _assert_count(summary, "document_count", len(documents), errors)

    variable_ids = [row.get("variable_id") for row in variables]
    source_ids = [row.get("source_id") for row in sources]
    document_ids = [row.get("document_id") for row in documents]
    if len(variable_ids) != len(set(variable_ids)):
        errors.append("variables.json contains duplicate variable_id values")
    if len(source_ids) != len(set(source_ids)):
        errors.append("sources.json contains duplicate source_id values")
    if len(document_ids) != len(set(document_ids)):
        errors.append("registry.json contains duplicate document_id values")

    configured_variable_ids = set(config.variables)
    configured_source_ids = set(config.sources)
    public_source_ids = {
        source_id
        for source_id, source in config.sources.items()
        if source.get("publish_enabled", False)
    }
    if set(variable_ids) != configured_variable_ids:
        errors.append("variables.json IDs do not match config/variables.yml")
    if set(source_ids) != configured_source_ids:
        errors.append("sources.json IDs do not match config/sources.yml")

    allowed_statuses = set(
        config.validation.get("publication", {}).get("allowed_statuses", ["validated", "approved"])
    )
    record_ids: set[str] = set()
    for index, row in enumerate(records):
        record_id = row.get("record_id")
        if not record_id:
            errors.append(f"records[{index}] has no record_id")
        elif record_id in record_ids:
            errors.append(f"Duplicate public record_id {record_id}")
        else:
            record_ids.add(record_id)
        if row.get("variable_id") not in configured_variable_ids:
            errors.append(f"Record {record_id} references an unknown variable")
        if row.get("source_id") not in configured_source_ids:
            errors.append(f"Record {record_id} references an unknown source")
        elif row.get("source_id") not in public_source_ids:
            errors.append(
                f"Record {record_id} references source {row.get('source_id')!r} "
                "whose publication gate is disabled"
            )
        document_id = row.get("document_id")
        if document_id and document_id not in set(document_ids):
            errors.append(f"Record {record_id} references missing document {document_id}")
        if row.get("validation_status") not in allowed_statuses:
            errors.append(
                f"Record {record_id} has non-public validation status "
                f"{row.get('validation_status')!r}"
            )
        if row.get("record_kind") in set(
            config.validation.get("publication", {}).get("exclude_record_kinds", [])
        ):
            errors.append(f"Record {record_id} has excluded record kind {row.get('record_kind')!r}")
        for field in ("value", "range_low", "range_high"):
            value = row.get(field)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                errors.append(f"Record {record_id} has invalid numeric {field}={value!r}")

    site_csv = _csv_rows(config.paths.site_data_dir / "records.csv")
    export_csv = _csv_rows(config.paths.export_dir / "records.csv")
    export_records = _read_json(config.paths.export_dir / "records.json", list)
    export_summary = _read_json(config.paths.export_dir / "summary.json", dict)
    if len(site_csv) != len(records):
        errors.append(f"site records.csv has {len(site_csv)} rows; expected {len(records)}")
    if len(export_csv) != len(records):
        errors.append(f"export records.csv has {len(export_csv)} rows; expected {len(records)}")
    if export_records != records:
        errors.append("data/export/records.json does not match site/data/records.json")
    if export_summary != summary:
        errors.append("data/export/summary.json does not match site/data/summary.json")

    run_ids = [row.get("run_id") for row in runs]
    if len(run_ids) != len(set(run_ids)):
        errors.append("runs.json contains duplicate run_id values")

    scan_paths = list(config.paths.site_data_dir.glob("*")) + list(
        config.paths.export_dir.glob("*")
    )
    _scan_for_secrets(scan_paths, errors)

    if errors:
        raise PublicationError("Public artifact validation failed:\n- " + "\n- ".join(errors))
    return {
        "records": len(records),
        "variables": len(variables),
        "sources": len(sources),
        "documents": len(documents),
        "runs": len(runs),
    }
