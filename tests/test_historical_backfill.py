from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bc_assumptions.historical_parsers import (
    HistoricalExtractionError,
    discover_fortis_annual_mda,
    parse_bc_budget_2026_raw,
    parse_bc_budget_standard_tables,
    parse_bchydro_annual_report,
    parse_bchydro_service_plan,
    parse_fortis_annual_mda,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "history"


def _values(records, variable_id: str) -> list[float]:
    return [item.value for item in records if item.variable_id == variable_id]


@pytest.mark.parametrize("year", [2021, 2024, 2025])
def test_bc_budget_multiple_layout_generations(year: int):
    text = (FIXTURES / f"bc_budget_{year}_tables.txt").read_text(encoding="utf-8")
    records = parse_bc_budget_standard_tables(text, year)
    assert len(records) == 60
    assert len({item.variable_id for item in records}) == 12
    assert all(item.target_year is not None for item in records)
    assert all(item.target_year >= year for item in records)
    assert _values(records, "economic.population.growth_yoy_pct")


def test_bc_budget_2026_changed_layout_is_a_separate_parser_generation():
    text = (FIXTURES / "bc_budget_2026_raw_tables.txt").read_text(encoding="utf-8")
    records = parse_bc_budget_2026_raw(text)
    assert len(records) == 26
    assert _values(records, "economic.population.growth_yoy_pct") == [-0.9, 0.4, 1.0]
    assert _values(records, "economic.unemployment_rate_pct") == [5.9, 5.8]


@pytest.mark.parametrize("year", [2021, 2023, 2026])
def test_bchydro_service_plan_layout_generations(year: int):
    text = (FIXTURES / f"bchydro_service_plan_{year}_excerpt.txt").read_text(
        encoding="utf-8"
    )
    records = parse_bchydro_service_plan(text, year)
    assert len(records) >= 56
    assert len({item.variable_id for item in records}) >= 14
    assert _values(records, "demand.utility.electricity_forecast_gwh")
    assert _values(records, "utility.system_imports_gwh")
    assert _values(records, "utility.capex_forecast_cad_millions")


@pytest.mark.parametrize(
    ("year", "sales", "capex"),
    [(2021, 51140.0, 3207.0), (2023, 54259.0, 3919.0), (2025, 56754.0, 4015.0)],
)
def test_bchydro_annual_actuals_across_report_generations(
    year: int, sales: float, capex: float
):
    text = (FIXTURES / f"bchydro_annual_{year}_rows.txt").read_text(encoding="utf-8")
    records = parse_bchydro_annual_report(text, year)
    assert _values(records, "demand.utility.electricity_sales_gwh") == [sales]
    assert _values(records, "utility.capex_actual_cad_millions") == [capex]


@pytest.mark.parametrize(
    ("utility", "year", "sales", "roe", "equity"),
    [
        ("fei", 2021, 228.0, 8.75, 38.5),
        ("fbc", 2021, 3460.0, 9.15, 40.0),
        ("fei", 2023, 213.0, 9.65, 45.0),
        ("fbc", 2023, 3478.0, 9.65, 41.0),
        ("fei", 2025, 217.0, 9.65, 45.0),
        ("fbc", 2025, 3619.0, 9.65, 41.0),
    ],
)
def test_fortis_annual_history_uses_annual_not_quarter_values(
    utility: str, year: int, sales: float, roe: float, equity: float
):
    text = (FIXTURES / f"fortis_{utility}_{year}_excerpt.txt").read_text(
        encoding="utf-8"
    )
    records = parse_fortis_annual_mda(text, utility, year)
    sales_variable = (
        "demand.utility.natural_gas_sales_pj"
        if utility == "fei"
        else "demand.utility.electricity_sales_gwh"
    )
    assert _values(records, sales_variable) == [sales]
    assert _values(records, "financial.allowed_roe_pct") == [roe]
    assert _values(records, "financial.deemed_equity_pct") == [equity]
    assert _values(records, "utility.customer_count")


def test_fortis_updated_rate_base_wins_and_discount_rate_is_scoped():
    text = (FIXTURES / "fortis_fei_2025_excerpt.txt").read_text(encoding="utf-8")
    records = parse_fortis_annual_mda(text, "fei", 2025)
    rate_base = [
        (item.target_year, item.value)
        for item in records
        if item.variable_id == "utility.rate_base_cad_millions"
    ]
    assert rate_base == [(2025, 6452.0), (2026, 6835.0)]
    assert [
        (item.target_year, item.value)
        for item in records
        if item.variable_id == "utility.capex_forecast_cad_millions"
    ] == [(2026, 1151.0)]
    assert [
        (item.target_year, item.value)
        for item in records
        if item.variable_id == "utility.capex_actual_cad_millions"
    ] == [(2025, 1261.0)]
    pension = next(
        item for item in records if item.variable_id == "financial.pension_discount_rate_pct"
    )
    assert pension.period_basis == "non_temporal"
    assert pension.metadata["not_social_or_project_discount_rate"] is True


def test_fortis_fbc_capex_actual_and_forecast_are_separate():
    text = (FIXTURES / "fortis_fbc_2025_excerpt.txt").read_text(encoding="utf-8")
    records = parse_fortis_annual_mda(text, "fbc", 2025)
    assert [
        (item.target_year, item.value, item.record_kind)
        for item in records
        if item.variable_id == "utility.capex_forecast_cad_millions"
    ] == [(2026, 207.0, "forecast")]
    assert [
        (item.target_year, item.value, item.record_kind)
        for item in records
        if item.variable_id == "utility.capex_actual_cad_millions"
    ] == [(2025, 186.0, "observation")]


def test_fortis_index_discovery_contract_requires_both_utilities_and_all_years():
    html = (FIXTURES / "fortis_investor_index_excerpt.html").read_text(encoding="utf-8")
    documents = discover_fortis_annual_mda(
        html, "https://www.fortisbc.com/investor-centre", start_year=2021, end_year=2025
    )
    assert len(documents) == 10
    broken = html.replace('<a href="/fbc-q4-2022-mda.pdf">MD&amp;A</a>', "")
    with pytest.raises(HistoricalExtractionError, match="missing"):
        discover_fortis_annual_mda(
            broken,
            "https://www.fortisbc.com/investor-centre",
            start_year=2021,
            end_year=2025,
        )


def test_historical_parsers_fail_closed_on_structural_drift():
    with pytest.raises(HistoricalExtractionError):
        parse_bc_budget_standard_tables("Budget table layout changed", 2024)
    with pytest.raises(HistoricalExtractionError):
        parse_bchydro_service_plan("Key Forecast Assumptions without tables", 2024)
    with pytest.raises(HistoricalExtractionError):
        parse_fortis_annual_mda("FORTISBC INC. but no annual sales table", "fbc", 2024)


def test_source_manifests_and_non_temporal_discount_parameter():
    config = yaml.safe_load((ROOT / "config" / "sources.yml").read_text(encoding="utf-8"))
    sources = {item["id"]: item for item in config["sources"]}
    budget = sources["bc_budget_economic_forecasts"]
    hydro = sources["bc_hydro_planning_assumptions"]
    fortis = sources["fortisbc_quarterly_financials"]
    discount = sources["bc_moti_benefit_cost_parameters"]

    assert budget["adapter"] == "bc_budget_history"
    assert len(budget["documents"]) == 6
    assert hydro["adapter"] == "bc_hydro_history"
    assert len(hydro["documents"]) == 11
    assert len(hydro["expected_document_ids"]) == 11
    assert fortis["adapter"] == "fortisbc_history"
    assert fortis["start_year"] == 2021 and fortis["end_year"] == 2025
    assert fortis["minimum_document_count"] == 10

    series = discount["documents"][0]["series"][0]
    assert discount["enabled"] is True
    assert series["variable_id"] == "financial.social_discount_rate_pct"
    assert series["non_temporal"] is True
    assert series["decision_context"]


def _artifact_result(source_id: str, label: str, content: bytes):
    from hashlib import sha256

    from bc_assumptions.http import BytesResult
    from bc_assumptions.models import Artifact

    digest = sha256(content).hexdigest()
    artifact = Artifact(
        source_id=source_id,
        source_url=f"https://example.invalid/{label}",
        local_path=f"fixtures/{label}",
        content_type="application/pdf",
        retrieved_at="2026-07-15T00:00:00Z",
        sha256=digest,
        size_bytes=len(content),
    )
    return BytesResult(artifact=artifact, content=content)


def test_budget_history_adapter_emits_registry_valid_forecast_records(monkeypatch):
    from bc_assumptions.adapters.bc_budget_history import BCBudgetHistoryAdapter
    from bc_assumptions.config import RegistryConfig
    from bc_assumptions.validation import validate_record

    config = RegistryConfig.load(ROOT)
    source = dict(config.sources["bc_budget_economic_forecasts"])
    source["documents"] = [dict(source["documents"][0])]
    source["expected_editions"] = [2021]
    fixture = (FIXTURES / "bc_budget_2021_tables.txt").read_text(encoding="utf-8")

    class FakeHTTP:
        def request_bytes(self, source_id, method, url, *, label, **kwargs):
            return _artifact_result(source_id, label, label.encode())

    monkeypatch.setattr(
        "bc_assumptions.adapters.bc_budget_history.extract_pdf_text",
        lambda *args, **kwargs: fixture,
    )
    result = BCBudgetHistoryAdapter(source, config.variables, None, FakeHTTP()).collect()
    assert len(result.records) == 60
    assert all(record.record_kind == "forecast" for record in result.records)
    assert all(record.metadata["evidence_type"] == "government_forecast" for record in result.records)
    for record in result.records:
        validate_record(record, config.variables, config.validation)


def test_bchydro_history_adapter_emits_registry_valid_plan_and_actual_records(monkeypatch):
    from bc_assumptions.adapters.bc_hydro_history import BCHydroHistoryAdapter
    from bc_assumptions.config import RegistryConfig
    from bc_assumptions.validation import validate_record

    config = RegistryConfig.load(ROOT)
    source = dict(config.sources["bc_hydro_planning_assumptions"])
    plan = dict(source["documents"][0])
    actual = next(
        dict(row)
        for row in source["documents"]
        if row["document_id"] == "bchydro_annual_service_plan_2020_21"
    )
    source["documents"] = [plan, actual]
    source["expected_document_ids"] = [plan["document_id"], actual["document_id"]]
    fixtures = {
        plan["document_id"]: (FIXTURES / "bchydro_service_plan_2021_excerpt.txt").read_text(
            encoding="utf-8"
        ),
        actual["document_id"]: (FIXTURES / "bchydro_annual_2021_rows.txt").read_text(
            encoding="utf-8"
        ),
    }

    class FakeHTTP:
        def request_bytes(self, source_id, method, url, *, label, **kwargs):
            return _artifact_result(source_id, label, label.encode())

    monkeypatch.setattr(
        "bc_assumptions.adapters.bc_hydro_history.extract_pdf_text",
        lambda content, **kwargs: fixtures[content.decode()],
    )
    result = BCHydroHistoryAdapter(source, config.variables, None, FakeHTTP()).collect()
    assert any(record.record_kind == "forecast" for record in result.records)
    assert any(record.record_kind == "observation" for record in result.records)
    for record in result.records:
        validate_record(record, config.variables, config.validation)


def test_fortis_history_adapter_emits_registry_valid_observations_and_parameters(monkeypatch):
    from bc_assumptions.adapters.fortisbc_history import FortisBCHistoryAdapter
    from bc_assumptions.config import RegistryConfig
    from bc_assumptions.validation import validate_record

    config = RegistryConfig.load(ROOT)
    source = dict(config.sources["fortisbc_quarterly_financials"])
    source.update({"start_year": 2021, "end_year": 2021, "minimum_document_count": 2})
    index = (FIXTURES / "fortis_investor_index_excerpt.html").read_bytes()
    text_by_label = {
        "fortis_fei_2021_annual_mda": (FIXTURES / "fortis_fei_2021_excerpt.txt").read_text(
            encoding="utf-8"
        ),
        "fortis_fbc_2021_annual_mda": (FIXTURES / "fortis_fbc_2021_excerpt.txt").read_text(
            encoding="utf-8"
        ),
    }

    class FakeHTTP:
        def request_bytes(self, source_id, method, url, *, label, **kwargs):
            content = index if label == "fortisbc_investor_index" else label.encode()
            return _artifact_result(source_id, label, content)

    monkeypatch.setattr(
        "bc_assumptions.adapters.fortisbc_history.extract_pdf_text",
        lambda content, **kwargs: text_by_label[content.decode()],
    )
    result = FortisBCHistoryAdapter(source, config.variables, None, FakeHTTP()).collect()
    assert any(record.record_kind == "observation" for record in result.records)
    assert any(record.record_kind == "model_parameter" for record in result.records)
    assert all(record.record_kind in {"observation", "forecast", "model_parameter"} for record in result.records)
    for record in result.records:
        validate_record(record, config.variables, config.validation)


def test_moti_social_discount_rate_recipe_extracts_exact_non_temporal_value():
    from bc_assumptions.adapters.document_assumptions import extract_series_values

    config = yaml.safe_load((ROOT / "config" / "sources.yml").read_text(encoding="utf-8"))
    source = next(
        item for item in config["sources"] if item["id"] == "bc_moti_benefit_cost_parameters"
    )
    document = source["documents"][0]
    series = document["series"][0]
    values, _ = extract_series_values(
        series,
        "The analysis applies a social discount rate of 6%/year to real benefits and costs.",
        document,
    )
    assert len(values) == 1
    assert values[0].value == 6.0
    assert values[0].target_period_start is None
    assert values[0].target_period_end is None
    assert values[0].reference_period_start == document["publication_date"]
    assert series["non_temporal"] is True
