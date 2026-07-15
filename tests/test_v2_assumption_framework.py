from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from bc_assumptions.adapters.bc_households import BCHouseholdsAdapter
from bc_assumptions.adapters.bcer_production import BCERProductionAdapter
from bc_assumptions.adapters.document_assumptions import extract_series_values
from bc_assumptions.adapters.icbc_vehicle_population import ICBCVehiclePopulationAdapter
from bc_assumptions.config import RegistryConfig, iter_source_outputs
from bc_assumptions.forecast_performance import build_forecast_performance
from bc_assumptions.models import Record
from bc_assumptions.validation import ValidationError, validate_record


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "v2"


def _rows(name: str) -> list[dict[str, str]]:
    with (FIXTURES / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _source(config: RegistryConfig, source_id: str) -> dict:
    return config.sources[source_id]


def test_v2_configuration_is_unique_complete_and_excludes_major_projects():
    config = RegistryConfig.load(ROOT)
    assert len(config.variables) == len(set(config.variables))
    assert len(config.sources) == len(set(config.sources))
    assert len(config.variables) >= 117
    assert len(config.sources) >= 21

    registered = set(config.variables)
    for source in config.sources.values():
        for output in iter_source_outputs(source):
            assert output["variable_id"] in registered

    matrix = yaml.safe_load((ROOT / "config" / "v2_source_matrix.yml").read_text())
    serialized = yaml.safe_dump(matrix).lower()
    assert "major_project" not in serialized
    assert "major projects" not in serialized


def test_v2_source_promotion_gates_are_fail_closed():
    config = RegistryConfig.load(ROOT)
    enabled = {
        "bc_budget_economic_forecasts",
        "bc_data_catalogue_households",
        "cer_provincial_gas_production",
        "bc_hydro_planning_assumptions",
        "bc_hydro_fortisbc_collaboration_assumptions",
        "bc_moti_benefit_cost_parameters",
        "fortisbc_quarterly_financials",
    }
    staged = {
        "bc_stats_population_projections",
        "icbc_vehicle_population",
        "bcer_production_data",
        "bc_hydro_quick_facts",
        "fortisbc_rate_review_assumptions",
        "bcuc_approved_financial_parameters",
    }
    assert all(config.sources[source_id]["enabled"] for source_id in enabled)
    assert all(not config.sources[source_id]["enabled"] for source_id in staged)


def test_budget_history_source_uses_explicit_document_manifest():
    config = RegistryConfig.load(ROOT)
    source = _source(config, "bc_budget_economic_forecasts")
    assert source["adapter"] == "bc_budget_history"
    assert [document["edition_year"] for document in source["documents"]] == list(
        range(2021, 2027)
    )

def test_bchydro_history_source_pairs_plan_vintages_with_actual_reports():
    config = RegistryConfig.load(ROOT)
    source = _source(config, "bc_hydro_planning_assumptions")
    document_types = [document["document_type"] for document in source["documents"]]
    assert source["adapter"] == "bc_hydro_history"
    assert document_types.count("service_plan") == 6
    assert document_types.count("annual_service_plan_report") == 5

def test_utility_collaboration_live_excerpt_preserves_scope():
    config = RegistryConfig.load(ROOT)
    source = _source(config, "bc_hydro_fortisbc_collaboration_assumptions")
    document = source["documents"][0]
    text = (FIXTURES / "utility_collaboration_2025_excerpt.txt").read_text(
        encoding="utf-8"
    )
    customer_series, load_series = document["series"]
    customer_values, match = extract_series_values(customer_series, text, document)
    load_values, _ = extract_series_values(load_series, text, document)

    assert [row.value for row in customer_values] == [0.8, 0.5, 0.5, 1.0, 0.3, 0.7, 0.5, 0.5]
    assert [row.value for row in load_values] == [6500, 1600, 2900, 11000]
    assert customer_series["metadata"]["not_population_growth_series"] is True
    assert "population" in customer_series["metadata"]["forecast_driver_basis"].lower()
    assert match.group("bch_lm") == "0.8"


def test_household_estimates_and_projections_are_separate_vintages():
    records = BCHouseholdsAdapter.records_from_rows(
        _rows("bc_households_sample.csv"),
        source_id="bc_data_catalogue_households",
        document_id="fixture",
        publication_date="2026-04-17",
        vintage_date="2026-04-17",
    )
    assert len(records) == 6
    estimates = [row for row in records if row.record_kind == "observation"]
    projections = [row for row in records if row.record_kind == "forecast"]
    assert len(estimates) == 3
    assert len(projections) == 3
    assert all(row.metadata["evidence_type"] == "observed" for row in estimates)
    assert all(row.metadata["evidence_type"] == "government_forecast" for row in projections)


def test_icbc_parser_separates_powertrains_and_derives_growth():
    config = RegistryConfig.load(ROOT)
    source = dict(_source(config, "icbc_vehicle_population"))
    source.update(
        {
            "minimum_years": 2,
            "preferred_geography_values": ["British Columbia"],
            "require_geography_column": True,
        }
    )
    adapter = ICBCVehiclePopulationAdapter(source, config.variables, None, None)
    records = adapter.parse_rows(_rows("icbc_vehicle_population.csv"), "fixture")
    by_variable = {}
    for record in records:
        by_variable.setdefault(record.variable_id, []).append(record)
    assert [row.value for row in by_variable["electrification.ev.bev_stock.level"]] == [100000, 135000]
    assert by_variable["electrification.ev.bev_stock_growth_yoy_pct"][0].value == pytest.approx(35.0)
    assert [row.value for row in by_variable["electrification.ev.phev_stock.level"]] == [25000, 31000]
    assert by_variable["electrification.ev.phev_stock_growth_yoy_pct"][0].value == pytest.approx(24.0)

    duplicate = _rows("icbc_vehicle_population.csv")
    duplicate.append(dict(duplicate[0]))
    with pytest.raises(ValueError, match="duplicate"):
        adapter.parse_rows(duplicate, "fixture")


def test_bcer_parser_is_monthly_and_rejects_duplicate_detail_rows():
    config = RegistryConfig.load(ROOT)
    source = dict(_source(config, "bcer_production_data"))
    source["minimum_months"] = 2
    adapter = BCERProductionAdapter(source, config.variables, None, None)
    records = adapter.parse_rows(_rows("bcer_production.csv"), "fixture")
    assert [row.value for row in records] == [1500.0, 1200.0]
    assert all(row.metadata["evidence_type"] == "observed" for row in records)

    duplicate = _rows("bcer_production.csv")
    duplicate.append(dict(duplicate[0]))
    with pytest.raises(ValueError, match="duplicate"):
        adapter.parse_rows(duplicate, "fixture")


def test_non_temporal_discount_rate_requires_context_not_target_year():
    config = RegistryConfig.load(ROOT)
    record = Record(
        variable_id="financial.social_discount_rate_pct",
        source_id="bc_moti_benefit_cost_parameters",
        source_series_id="bc_moti_social_discount_rate_2018",
        value=3.5,
        unit_original="percent",
        unit_canonical="percent",
        reference_period_start="2018-05-07",
        reference_period_end="2018-05-07",
        record_kind="model_parameter",
        publication_date="2018-05-07",
        vintage_date="2018-05-07",
        period_basis="non_temporal",
        metadata={
            "time_basis": "non_temporal_parameter",
            "decision_context": "B.C. transportation benefit-cost analysis",
            "evidence_type": "government_policy_assumption",
        },
    )
    assert validate_record(record, config.variables, config.validation).value == 3.5
    with pytest.raises(ValidationError, match="cannot have a target period"):
        validate_record(
            replace(
                record,
                target_period_start="2026-01-01",
                target_period_end="2026-12-31",
            ),
            config.variables,
            config.validation,
        )


def test_fortis_source_discovers_complete_annual_history():
    config = RegistryConfig.load(ROOT)
    source = _source(config, "fortisbc_quarterly_financials")
    assert source["adapter"] == "fortisbc_history"
    assert source["start_year"] == 2021
    assert source["end_year"] == 2025
    assert source["minimum_document_count"] == 10

def test_forecast_performance_requires_exact_period_geography_and_entity():
    forecast = {
        "record_id": "f1",
        "record_kind": "forecast",
        "variable_id": "economic.population.growth_yoy_pct",
        "unit_canonical": "percent",
        "geography_id": "CA-BC",
        "entity_id": None,
        "target_period_start": "2027-01-01",
        "target_period_end": "2027-12-31",
        "publication_date": "2026-02-17",
        "vintage_date": "2026-02-17",
        "source_id": "bc_budget_economic_forecasts",
        "scenario_original": "Budget forecast",
        "value": 0.4,
    }
    actual = {
        "record_id": "a1",
        "record_kind": "observation",
        "variable_id": forecast["variable_id"],
        "unit_canonical": "percent",
        "geography_id": "CA-BC",
        "entity_id": None,
        "reference_period_start": "2027-01-01",
        "reference_period_end": "2027-12-31",
        "source_id": "statistics_canada_wds",
        "value": 0.1,
    }
    wrong_scope = {**actual, "record_id": "a2", "entity_id": "bc_hydro", "value": 1.0}
    result = build_forecast_performance(
        [forecast, actual, wrong_scope],
        source_authority={"statistics_canada_wds": 1},
    )
    assert len(result) == 1
    assert result[0]["actual_record_id"] == "a1"
    assert result[0]["signed_error"] == pytest.approx(0.3)
    assert result[0]["actual_candidate_count"] == 1


def test_regulatory_templates_cover_high_priority_utility_gaps():
    from bc_assumptions.regulatory.recipe import load_recipe

    template_dir = ROOT / "config" / "regulatory_recipes"
    templates = [
        load_recipe(template_dir / "bcuc_financial_parameters_template.yml"),
        load_recipe(template_dir / "bchydro_irp_assumptions_template.yml"),
        load_recipe(template_dir / "fortisbc_rate_review_template.yml"),
    ]
    variables = {
        extractor["variable_id"]
        for recipe in templates
        for extractor in recipe["extractors"]
    }
    assert {
        "financial.cost_of_debt_pct",
        "financial.wacc_pct",
        "financial.utility_regulatory_discount_rate_pct",
        "demand.utility.peak_forecast_mw",
        "reliability.reserve_margin_pct",
        "reliability.elcc_pct_nameplate",
        "utility.dsm_savings_gwh",
        "utility.capacity_gap_mw",
        "utility.energy_supply_gap_gwh",
        "utility.rate_change_pct",
        "financial.pension_discount_rate_pct",
    } <= variables


def test_observed_result_is_allowed_evidence_type():
    from bc_assumptions.validation import ALLOWED_EVIDENCE_TYPES

    assert "observed_result" in ALLOWED_EVIDENCE_TYPES
