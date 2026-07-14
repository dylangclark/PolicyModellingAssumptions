#!/usr/bin/env python3
"""Build the static source-gap matrix used by the GitHub Pages UI."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {path}")
    return data


def load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"variables": [], "records": [], "sources": [], "summary": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return data


def candidate_source_details(candidate: dict[str, Any], families: dict[str, Any]) -> dict[str, Any]:
    source_id = candidate.get("preferred_source")
    family = families.get(source_id, {}) if source_id else {}
    return {
        "preferred_source_id": source_id,
        "preferred_source_name": family.get("publisher") or source_id,
        "source_url": family.get("source_url"),
        "source_format": family.get("format"),
        "source_licence": family.get("licence"),
        "collector_pattern": family.get("collector_pattern"),
        "source_implementation_status": family.get("implementation_status"),
    }


def build_report(variables_data: dict[str, Any], candidates_data: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    configured = variables_data.get("variables", [])
    if not isinstance(configured, list):
        raise ValueError("variables.yml must contain a variables list")
    candidates = candidates_data.get("variables", {})
    families = candidates_data.get("source_families", {})
    public_records = registry.get("records", []) or []
    record_counts: dict[str, int] = {}
    for record in public_records:
        variable_id = record.get("variable_id")
        if variable_id:
            record_counts[variable_id] = record_counts.get(variable_id, 0) + 1

    rows: list[dict[str, Any]] = []
    for variable in configured:
        variable_id = variable["id"]
        candidate = candidates.get(variable_id, {})
        public_count = record_counts.get(variable_id, 0)
        if public_count:
            workflow_status = "data_available"
        else:
            workflow_status = candidate.get("status", "no_suitable_source")
        row = {
            "variable_id": variable_id,
            "class_name": variable.get("class"),
            "name": variable.get("name"),
            "description": variable.get("description"),
            "canonical_unit": variable.get("canonical_unit"),
            "geography_id": variable.get("geography_id"),
            "variable_status": variable.get("status"),
            "phase": variable.get("phase"),
            "public_record_count": public_count,
            "workflow_status": workflow_status,
            "priority": candidate.get("priority"),
            "collector_difficulty": candidate.get("collector_difficulty"),
            "publication_gate": candidate.get("publication_gate"),
            "source_series_scope": candidate.get("source_series_scope"),
            "alternative_sources": candidate.get("alternative_sources", []),
            "derived_from": candidate.get("derived_from"),
            "formula": candidate.get("formula"),
            "notes": candidate.get("notes"),
            **candidate_source_details(candidate, families),
        }
        rows.append(row)

    rows.sort(key=lambda row: (
        0 if row["workflow_status"] == "data_available" else 1,
        row["priority"] if isinstance(row["priority"], int) else 99,
        row["class_name"] or "",
        row["name"] or row["variable_id"],
    ))

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["workflow_status"]] = counts.get(row["workflow_status"], 0) + 1

    return {
        "schema_version": candidates_data.get("schema_version", "0.1.0"),
        "configured_variable_count": len(rows),
        "variables_with_public_data": sum(1 for row in rows if row["public_record_count"] > 0),
        "variables_without_public_data": sum(1 for row in rows if row["public_record_count"] == 0),
        "status_counts": counts,
        "workflow_statuses": candidates_data.get("workflow_statuses", []),
        "priorities": candidates_data.get("priorities", []),
        "excluded_variables": candidates_data.get("excluded_variables", []),
        "additional_variables_to_register": candidates_data.get("additional_variables_to_register", []),
        "source_families": families,
        "variables": rows,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "variable_id", "class_name", "name", "canonical_unit", "geography_id",
        "public_record_count", "workflow_status", "priority", "preferred_source_id",
        "preferred_source_name", "source_url", "source_format", "source_licence",
        "collector_pattern", "collector_difficulty", "publication_gate",
        "source_series_scope", "derived_from", "formula", "alternative_sources", "notes",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            flat = {key: row.get(key) for key in fields}
            flat["alternative_sources"] = " | ".join(row.get("alternative_sources") or [])
            writer.writerow(flat)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    variables = load_yaml(root / "config" / "variables.yml")
    candidates = load_yaml(root / "config" / "source_candidates.yml")
    registry = load_registry(root / "site" / "data" / "registry.json")
    report = build_report(variables, candidates, registry)
    out_json = root / "site" / "data" / "source-gaps.json"
    out_csv = root / "data" / "export" / "source-gaps.csv"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(out_csv, report["variables"])
    print(json.dumps({
        "source_gap_report": str(out_json.relative_to(root)),
        "source_gap_csv": str(out_csv.relative_to(root)),
        "configured_variables": report["configured_variable_count"],
        "with_public_data": report["variables_with_public_data"],
        "without_public_data": report["variables_without_public_data"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
