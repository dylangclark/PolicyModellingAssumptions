#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import yaml


HISTORY_SOURCES = {
    "bc_budget_economic_forecasts",
    "bc_hydro_planning_assumptions",
    "fortisbc_quarterly_financials",
    "bc_moti_benefit_cost_parameters",
}


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build document-level coverage for the v2 historical backfill."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser.parse_args()


def _load_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"Expected a list in {path}")
    return [row for row in value if isinstance(row, dict)]


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("metadata")
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _expected_rows(sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    budget = sources["bc_budget_economic_forecasts"]
    for document in budget["documents"]:
        rows.append(
            {
                "source_id": budget["id"],
                "document_key": document["document_id"],
                "document_type": "budget_and_fiscal_plan",
                "edition": document["edition"],
                "publication_date": document["publication_date"],
                "match": {"edition_year": int(document["edition_year"])},
            }
        )

    hydro = sources["bc_hydro_planning_assumptions"]
    for document in hydro["documents"]:
        rows.append(
            {
                "source_id": hydro["id"],
                "document_key": document["document_id"],
                "document_type": document["document_type"],
                "edition": document["edition"],
                "publication_date": document["publication_date"],
                "match": {
                    "document_type": document["document_type"],
                    "edition": document["edition"],
                },
            }
        )

    fortis = sources["fortisbc_quarterly_financials"]
    for utility in ("fei", "fbc"):
        for year in range(int(fortis["start_year"]), int(fortis["end_year"]) + 1):
            rows.append(
                {
                    "source_id": fortis["id"],
                    "document_key": f"fortis_{utility}_{year}_annual_mda",
                    "document_type": "annual_mda",
                    "edition": str(year),
                    "publication_date": None,
                    "match": {"utility": utility, "filing_year": year},
                }
            )

    discount = sources["bc_moti_benefit_cost_parameters"]
    for document in discount["documents"]:
        rows.append(
            {
                "source_id": discount["id"],
                "document_key": document["document_id"],
                "document_type": "government_guidance",
                "edition": document.get("edition"),
                "publication_date": document.get("publication_date"),
                "match": {},
            }
        )
    return rows


def _matches(record: dict[str, Any], expected: dict[str, Any]) -> bool:
    if record.get("source_id") != expected["source_id"]:
        return False
    metadata = _metadata(record)
    for key, value in expected["match"].items():
        if metadata.get(key) != value:
            return False
    return True


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source_id",
        "document_key",
        "document_type",
        "edition",
        "publication_date",
        "status",
        "record_count",
        "variable_count",
        "forecast_count",
        "observation_count",
        "model_parameter_count",
    ]
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def main() -> int:
    args = _args()
    root = args.root.resolve()
    config = yaml.safe_load((root / "config" / "sources.yml").read_text(encoding="utf-8"))
    sources = {row["id"]: row for row in config["sources"]}
    missing = HISTORY_SOURCES - set(sources)
    if missing:
        raise SystemExit(f"Missing historical sources: {sorted(missing)}")

    all_records = _load_json(root / "data" / "export" / "records.json")
    all_records += _load_json(root / "data" / "export" / "records_history.json")
    unique: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(all_records):
        key = str(row.get("record_id") or f"row-{index}")
        unique[key] = row
    records = list(unique.values())

    rows: list[dict[str, Any]] = []
    for expected in _expected_rows(sources):
        matched = [row for row in records if _matches(row, expected)]
        kinds: dict[str, int] = {}
        for row in matched:
            kind = str(row.get("record_kind") or "unknown")
            kinds[kind] = kinds.get(kind, 0) + 1
        rows.append(
            {
                "source_id": expected["source_id"],
                "document_key": expected["document_key"],
                "document_type": expected["document_type"],
                "edition": expected["edition"],
                "publication_date": expected["publication_date"],
                "status": "parsed" if matched else "missing",
                "record_count": len(matched),
                "variable_count": len({row.get("variable_id") for row in matched}),
                "forecast_count": kinds.get("forecast", 0),
                "observation_count": kinds.get("observation", 0),
                "model_parameter_count": kinds.get("model_parameter", 0),
            }
        )

    parsed = sum(row["status"] == "parsed" for row in rows)
    report = {
        "schema_version": "1.0",
        "expected_document_count": len(rows),
        "parsed_document_count": parsed,
        "missing_document_count": len(rows) - parsed,
        "historical_record_count": sum(row["record_count"] for row in rows),
        "source_summary": {
            source_id: {
                "expected": sum(row["source_id"] == source_id for row in rows),
                "parsed": sum(
                    row["source_id"] == source_id and row["status"] == "parsed"
                    for row in rows
                ),
                "records": sum(
                    row["record_count"] for row in rows if row["source_id"] == source_id
                ),
            }
            for source_id in sorted(HISTORY_SOURCES)
        },
        "documents": rows,
    }

    _write_json(root / "site" / "data" / "history-coverage.json", report)
    _write_json(root / "data" / "export" / "history-coverage.json", report)
    _write_csv(root / "data" / "export" / "history-coverage.csv", rows)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
