#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Any

from bc_assumptions.config import RegistryConfig
from bc_assumptions.historical_parsers import (
    discover_fortis_annual_mda,
    parse_bc_budget_2026_raw,
    parse_bc_budget_standard_tables,
    parse_bchydro_annual_report,
    parse_bchydro_service_plan,
    parse_fortis_annual_mda,
)
from bc_assumptions.pdf_text import extract_pdf_text


VERSION = "2.0.0rc2"
HISTORICAL_SOURCE_IDS = {
    "budget": "bc_budget_economic_forecasts",
    "hydro": "bc_hydro_planning_assumptions",
    "fortis": "fortisbc_quarterly_financials",
    "discount": "bc_moti_benefit_cost_parameters",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the v2 historical manifests, parser fixtures, and optionally "
            "the complete set of downloaded official historical PDFs."
        )
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--live-doc-dir",
        type=Path,
        help=(
            "Optional directory containing bc_budget_2021.pdf through "
            "bc_budget_2026.pdf, six BC Hydro service plans, and five annual reports."
        ),
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path for a machine-readable validation report.",
    )
    return parser.parse_args()


def _manifest_validation(config: RegistryConfig) -> dict[str, Any]:
    budget = config.sources[HISTORICAL_SOURCE_IDS["budget"]]
    hydro = config.sources[HISTORICAL_SOURCE_IDS["hydro"]]
    fortis = config.sources[HISTORICAL_SOURCE_IDS["fortis"]]
    discount = config.sources[HISTORICAL_SOURCE_IDS["discount"]]

    budget_years = [int(row["edition_year"]) for row in budget["documents"]]
    if budget_years != list(range(2021, 2027)):
        raise ValueError(f"Unexpected B.C. Budget manifest: {budget_years}")

    hydro_ids = [row["document_id"] for row in hydro["documents"]]
    if hydro_ids != list(hydro["expected_document_ids"]):
        raise ValueError("BC Hydro expected_document_ids and document manifest disagree")
    hydro_types = [row["document_type"] for row in hydro["documents"]]
    if hydro_types.count("service_plan") != 6:
        raise ValueError("BC Hydro manifest must contain six service plans")
    if hydro_types.count("annual_service_plan_report") != 5:
        raise ValueError("BC Hydro manifest must contain five annual result reports")

    if (int(fortis["start_year"]), int(fortis["end_year"])) != (2021, 2025):
        raise ValueError("FortisBC history must span 2021 through 2025")
    if int(fortis["minimum_document_count"]) != 10:
        raise ValueError("FortisBC history must require ten annual MD&A documents")

    discount_series = discount["documents"][0]["series"][0]
    if not discount_series.get("non_temporal"):
        raise ValueError("The B.C. social discount rate must be non-temporal")
    if not discount_series.get("decision_context"):
        raise ValueError("The B.C. social discount rate is missing decision context")

    return {
        "bc_budget": {"documents": len(budget["documents"]), "years": budget_years},
        "bc_hydro": {
            "documents": len(hydro["documents"]),
            "service_plans": hydro_types.count("service_plan"),
            "annual_result_reports": hydro_types.count("annual_service_plan_report"),
        },
        "fortisbc": {
            "expected_documents": int(fortis["minimum_document_count"]),
            "start_year": int(fortis["start_year"]),
            "end_year": int(fortis["end_year"]),
        },
        "social_discount_rate": {
            "non_temporal": True,
            "decision_context": discount_series["decision_context"],
        },
    }


def _validate_fixture_regressions(root: Path) -> dict[str, Any]:
    fixtures = root / "tests" / "fixtures" / "history"
    if not fixtures.exists():
        raise FileNotFoundError(f"Historical parser fixtures are missing: {fixtures}")

    budget_counts: dict[str, int] = {}
    for year in (2021, 2024, 2025):
        text = (fixtures / f"bc_budget_{year}_tables.txt").read_text(encoding="utf-8")
        budget_counts[str(year)] = len(parse_bc_budget_standard_tables(text, year))
    budget_counts["2026"] = len(
        parse_bc_budget_2026_raw(
            (fixtures / "bc_budget_2026_raw_tables.txt").read_text(encoding="utf-8")
        )
    )

    hydro_plan_counts: dict[str, int] = {}
    for year in (2021, 2023, 2026):
        text = (fixtures / f"bchydro_service_plan_{year}_excerpt.txt").read_text(
            encoding="utf-8"
        )
        hydro_plan_counts[str(year)] = len(parse_bchydro_service_plan(text, year))

    hydro_actual_counts: dict[str, int] = {}
    for year in (2021, 2023, 2025):
        text = (fixtures / f"bchydro_annual_{year}_rows.txt").read_text(
            encoding="utf-8"
        )
        hydro_actual_counts[str(year)] = len(parse_bchydro_annual_report(text, year))

    fortis_counts: dict[str, int] = {}
    for utility in ("fei", "fbc"):
        for year in (2021, 2023, 2025):
            text = (fixtures / f"fortis_{utility}_{year}_excerpt.txt").read_text(
                encoding="utf-8"
            )
            fortis_counts[f"{utility}_{year}"] = len(
                parse_fortis_annual_mda(text, utility, year)
            )

    index_html = (fixtures / "fortis_investor_index_excerpt.html").read_text(
        encoding="utf-8"
    )
    discovered = discover_fortis_annual_mda(
        index_html,
        "https://www.fortisbc.com/about-us/corporate-information/investor-centre",
        start_year=2021,
        end_year=2025,
    )
    if len(discovered) != 10:
        raise ValueError(f"FortisBC fixture index discovered {len(discovered)} documents")

    return {
        "bc_budget_record_counts": budget_counts,
        "bc_hydro_service_plan_record_counts": hydro_plan_counts,
        "bc_hydro_annual_result_record_counts": hydro_actual_counts,
        "fortisbc_record_counts": fortis_counts,
        "fortisbc_discovered_documents": len(discovered),
    }


def _history_filename(document: dict[str, Any]) -> str:
    document_id = document["document_id"]
    if document_id.startswith("bchydro_annual_service_plan_"):
        suffix = document_id.removeprefix("bchydro_annual_service_plan_")
        return f"bchydro_annual_{suffix}.pdf"
    return f"{document_id}.pdf"


def _validate_live_documents(config: RegistryConfig, directory: Path) -> dict[str, Any]:
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext is required for historical PDF validation")

    report: dict[str, Any] = {
        "bc_budget": {},
        "bc_hydro_service_plans": {},
        "bc_hydro_annual_results": {},
    }

    budget = config.sources[HISTORICAL_SOURCE_IDS["budget"]]
    for document in budget["documents"]:
        year = int(document["edition_year"])
        path = directory / f"bc_budget_{year}.pdf"
        if not path.is_file():
            raise FileNotFoundError(f"Missing official historical PDF: {path}")
        content = path.read_bytes()
        if year <= 2025:
            text = extract_pdf_text(content, require_pdftotext=True, mode="layout")
            values = parse_bc_budget_standard_tables(text, year)
        else:
            text = extract_pdf_text(content, require_pdftotext=True, mode="raw")
            values = parse_bc_budget_2026_raw(text)
        report["bc_budget"][str(year)] = {
            "records": len(values),
            "variables": len({row.variable_id for row in values}),
        }

    hydro = config.sources[HISTORICAL_SOURCE_IDS["hydro"]]
    for document in hydro["documents"]:
        path = directory / _history_filename(document)
        if not path.is_file():
            raise FileNotFoundError(f"Missing official historical PDF: {path}")
        text = extract_pdf_text(path.read_bytes(), require_pdftotext=True, mode="layout")
        if document["document_type"] == "service_plan":
            year = int(document["edition_start_year"])
            values = parse_bchydro_service_plan(text, year)
            bucket = report["bc_hydro_service_plans"]
            key = str(year)
        else:
            year = int(document["fiscal_end_year"])
            values = parse_bchydro_annual_report(text, year)
            bucket = report["bc_hydro_annual_results"]
            key = str(year)
        bucket[key] = {
            "records": len(values),
            "variables": len({row.variable_id for row in values}),
        }

    return report


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = _parse_args()
    try:
        root = args.root.resolve()
        config = RegistryConfig.load(root)
        payload: dict[str, Any] = {
            "version": VERSION,
            "configuration_valid": True,
            "configured_variables": len(config.variables),
            "configured_sources": len(config.sources),
            "enabled_sources": sum(
                1 for source in config.sources.values() if source.get("enabled")
            ),
            "pdftotext_available": bool(shutil.which("pdftotext")),
            "manifest_validation": _manifest_validation(config),
            "fixture_regression_validation": _validate_fixture_regressions(root),
            "official_pdf_validation": None,
        }
        if args.live_doc_dir:
            payload["official_pdf_validation"] = _validate_live_documents(
                config, args.live_doc_dir.resolve()
            )
        if args.json_output:
            _write_json(args.json_output.resolve(), payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001 - validator must report all release failures.
        failure = {"version": VERSION, "configuration_valid": False, "error": str(exc)}
        if args.json_output:
            _write_json(args.json_output.resolve(), failure)
        print(json.dumps(failure, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
