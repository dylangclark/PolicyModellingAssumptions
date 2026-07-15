from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup


class HistoricalExtractionError(ValueError):
    """Raised when a historical publication does not meet its extraction contract."""


_NUMBER = re.compile(r"\(?-?\$?[0-9][0-9,]*(?:\.[0-9]+)?%?\)?")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


@dataclass(frozen=True, slots=True)
class HistoricalValue:
    variable_id: str
    source_series_id: str
    value: float
    target_year: int | None
    unit: str
    record_kind: str
    period_basis: str = "annual"
    scenario: str | None = None
    entity_id: str | None = None
    evidence_text: str | None = None
    evidence_table: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def normalize_lines(text: str) -> str:
    substitutions = {
        "\u00a0": " ",
        "\u2212": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\u2026": "...",
        "/uni00A0": " ",
    }
    for old, new in substitutions.items():
        text = text.replace(old, new)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())


def parse_number(token: str) -> float:
    value = token.strip()
    negative = value.startswith("(") and value.endswith(")")
    value = value.strip("()").replace(",", "").replace("$", "").replace("%", "")
    try:
        number = float(value)
    except ValueError as exc:
        raise HistoricalExtractionError(f"Invalid numeric token: {token!r}") from exc
    return -number if negative else number


def numbers(line: str) -> list[float]:
    return [parse_number(token) for token in _NUMBER.findall(line)]


def _section(text: str, start_pattern: str, end_pattern: str | None = None) -> str:
    start = re.search(start_pattern, text, re.IGNORECASE)
    if not start:
        raise HistoricalExtractionError(f"Missing section matching {start_pattern!r}")
    tail = text[start.start() :]
    if end_pattern:
        end = re.search(end_pattern, tail[start.end() - start.start() :], re.IGNORECASE)
        if end:
            return tail[: start.end() - start.start() + end.start()]
    return tail


def _header_years(section: str, minimum: int = 4) -> list[int]:
    for line in section.splitlines()[:15]:
        values = [int(value) for value in _YEAR.findall(line)]
        if len(values) >= minimum:
            if len(values) != len(set(values)):
                # Some tables print current and comparison blocks. The first distinct run
                # is the intended year header.
                distinct: list[int] = []
                for value in values:
                    if value not in distinct:
                        distinct.append(value)
                values = distinct
            return values
    raise HistoricalExtractionError("Could not identify a year header")


def _find_line(section: str, pattern: str, *, start_at: int = 0) -> tuple[int, str]:
    compiled = re.compile(pattern, re.IGNORECASE)
    lines = section.splitlines()
    for index in range(start_at, len(lines)):
        if compiled.search(lines[index]):
            return index, lines[index]
    raise HistoricalExtractionError(f"Missing row matching {pattern!r}")


def _row_values(
    section: str,
    pattern: str,
    expected: int,
    *,
    percent_following: bool = False,
) -> tuple[list[float], str]:
    index, line = _find_line(section, pattern)
    evidence = line
    if percent_following:
        lines = section.splitlines()
        for candidate in lines[index + 1 : index + 5]:
            if re.search(r"%\s*change", candidate, re.IGNORECASE):
                line = candidate
                evidence += " | " + candidate
                break
        else:
            raise HistoricalExtractionError(f"Missing percent-change row after {pattern!r}")
    values = numbers(line)
    if not percent_following and len(values) < expected:
        lines = section.splitlines()
        combined = line
        for candidate in lines[index + 1 : index + 4]:
            combined += " " + candidate
            values = numbers(combined)
            if len(values) >= expected:
                line = combined
                evidence = combined
                break
    # Drop footnote digits that appear before the actual table values.
    if len(values) > expected:
        values = values[-expected:]
    if len(values) != expected:
        raise HistoricalExtractionError(
            f"Row {pattern!r} expected {expected} values, found {len(values)}: {line!r}"
        )
    return values, evidence


def _forecast_values(
    years: list[int],
    values: list[float],
    publication_year: int,
    *,
    variable_id: str,
    source_series_id: str,
    unit: str,
    evidence: str,
    table: str,
    transform: str | None = None,
) -> list[HistoricalValue]:
    output: list[HistoricalValue] = []
    for year, value in zip(years, values):
        if year < publication_year:
            continue
        if transform == "us_cents_to_cad_per_usd":
            if value <= 0:
                raise HistoricalExtractionError("Exchange-rate assumption cannot be zero")
            value = 100.0 / value
        output.append(
            HistoricalValue(
                variable_id=variable_id,
                source_series_id=f"{source_series_id}_{year}",
                value=value,
                target_year=year,
                unit=unit,
                record_kind="forecast",
                scenario="B.C. Ministry of Finance forecast",
                evidence_text=evidence[:1000],
                evidence_table=table,
                metadata={"forecast_owner": "B.C. Ministry of Finance"},
            )
        )
    return output


def parse_bc_budget_standard_tables(text: str, publication_year: int) -> list[HistoricalValue]:
    """Parse the stable economic tables used by B.C. budgets from 2021 through 2025."""

    text = normalize_lines(text)
    output: list[HistoricalValue] = []

    gdp = _section(text, r"Table\s+3\.6\.1\s+Gross Domestic Product", r"Table\s+3\.6\.2")
    years = _header_years(gdp)
    real, evidence = _row_values(gdp, r"-\s*Real\s*\(", len(years), percent_following=True)
    output += _forecast_values(
        years,
        real,
        publication_year,
        variable_id="economic.real_gdp_growth_pct",
        source_series_id=f"budget{publication_year}_real_gdp_growth",
        unit="percent",
        evidence=evidence,
        table="Table 3.6.1",
    )
    nominal, evidence = _row_values(gdp, r"-\s*Nominal\s*\(", len(years), percent_following=True)
    output += _forecast_values(
        years,
        nominal,
        publication_year,
        variable_id="economic.nominal_gdp_growth_pct",
        source_series_id=f"budget{publication_year}_nominal_gdp_growth",
        unit="percent",
        evidence=evidence,
        table="Table 3.6.1",
    )
    exports, evidence = _row_values(
        gdp, r"Exports of goods and services", len(years), percent_following=True
    )
    output += _forecast_values(
        years,
        exports,
        publication_year,
        variable_id="economic.exports_growth_pct",
        source_series_id=f"budget{publication_year}_exports_growth",
        unit="percent",
        evidence=evidence,
        table="Table 3.6.1",
    )

    nominal_indicators = _section(
        text, r"Table\s+3\.6\.2\s+Selected Nominal Income", r"Table\s+3\.6\.3"
    )
    years2 = _header_years(nominal_indicators)
    if years2 != years:
        raise HistoricalExtractionError("Budget table year headers disagree")
    retail, evidence = _row_values(
        nominal_indicators, r"^Retail sales\s*\(", len(years), percent_following=True
    )
    output += _forecast_values(
        years,
        retail,
        publication_year,
        variable_id="economic.retail_sales_growth_pct",
        source_series_id=f"budget{publication_year}_retail_sales_growth",
        unit="percent",
        evidence=evidence,
        table="Table 3.6.2",
    )
    starts, evidence = _row_values(nominal_indicators, r"^Housing starts\s*\(", len(years))
    output += _forecast_values(
        years,
        starts,
        publication_year,
        variable_id="economic.housing_starts.annual_units",
        source_series_id=f"budget{publication_year}_housing_starts",
        unit="dwelling_units",
        evidence=evidence,
        table="Table 3.6.2",
    )
    cpi, evidence = _row_values(
        nominal_indicators, r"^Consumer price index", len(years), percent_following=True
    )
    output += _forecast_values(
        years,
        cpi,
        publication_year,
        variable_id="economic.cpi.all_items_yoy_pct",
        source_series_id=f"budget{publication_year}_cpi_growth",
        unit="percent",
        evidence=evidence,
        table="Table 3.6.2",
    )

    labour = _section(text, r"Table\s+3\.6\.3\s+Labour Market Indicators", r"Table\s+3\.6\.4")
    years3 = _header_years(labour)
    if years3 != years:
        raise HistoricalExtractionError("Budget labour table year header disagrees")
    population, evidence = _row_values(
        labour, r"^Population\s*\(thousands at July 1\)", len(years), percent_following=True
    )
    output += _forecast_values(
        years,
        population,
        publication_year,
        variable_id="economic.population.growth_yoy_pct",
        source_series_id=f"budget{publication_year}_population_growth",
        unit="percent",
        evidence=evidence,
        table="Table 3.6.3",
    )
    participation, evidence = _row_values(labour, r"^Participation rate", len(years))
    output += _forecast_values(
        years,
        participation,
        publication_year,
        variable_id="economic.labour_force_participation_rate_pct",
        source_series_id=f"budget{publication_year}_participation_rate",
        unit="percent",
        evidence=evidence,
        table="Table 3.6.3",
    )
    employment, evidence = _row_values(
        labour, r"^Employment\s*\(thousands\)", len(years), percent_following=True
    )
    output += _forecast_values(
        years,
        employment,
        publication_year,
        variable_id="economic.employment.growth_yoy_pct",
        source_series_id=f"budget{publication_year}_employment_growth",
        unit="percent",
        evidence=evidence,
        table="Table 3.6.3",
    )
    unemployment, evidence = _row_values(labour, r"^Unemployment rate", len(years))
    output += _forecast_values(
        years,
        unemployment,
        publication_year,
        variable_id="economic.unemployment_rate_pct",
        source_series_id=f"budget{publication_year}_unemployment_rate",
        unit="percent",
        evidence=evidence,
        table="Table 3.6.3",
    )

    assumptions = _section(text, r"Table\s+3\.6\.4\s+Major Economic Assumptions")
    years4 = _header_years(assumptions)
    if years4 != years:
        raise HistoricalExtractionError("Budget assumptions table year header disagrees")
    bond, evidence = _row_values(
        assumptions, r"^\s*10-year government bonds", len(years), percent_following=False
    )
    # The first occurrence is within the Canadian interest-rate block.
    output += _forecast_values(
        years,
        bond,
        publication_year,
        variable_id="economic.interest_rate.goc_10y_yield_pct",
        source_series_id=f"budget{publication_year}_goc_10y_rate",
        unit="percent",
        evidence=evidence,
        table="Table 3.6.4",
    )
    exchange, evidence = _row_values(assumptions, r"^Exchange rate\s*\(US cents", len(years))
    output += _forecast_values(
        years,
        exchange,
        publication_year,
        variable_id="economic.exchange_rate.cad_per_usd",
        source_series_id=f"budget{publication_year}_cad_per_usd",
        unit="CAD_per_USD",
        evidence=evidence,
        table="Table 3.6.4",
        transform="us_cents_to_cad_per_usd",
    )
    if len(output) < 20:
        raise HistoricalExtractionError(
            f"Budget {publication_year} extraction produced only {len(output)} records"
        )
    return output


def parse_bc_budget_2026_raw(text: str) -> list[HistoricalValue]:
    """Parse the 2026 budget's changed/corrupted table layout from raw Poppler text."""

    text = normalize_lines(text)
    output: list[HistoricalValue] = []
    # First four values in Table 1.5.1 are the Ministry forecast for 2025-2028;
    # a second four-value block is the previous Budget comparison.
    years = [2025, 2026, 2027, 2028]
    table = _section(text, r"Table\s+1\.5\.1|a le 1\.5\.1", r"Fiscal Year")
    rows = [
        ("economic.real_gdp_growth_pct", "real_gdp_growth", r"^Real GDP\s+\.", "percent", None),
        ("economic.nominal_gdp_growth_pct", "nominal_gdp_growth", r"^Nominal GDP\s+\.", "percent", None),
        ("economic.employment.growth_yoy_pct", "employment_growth", r"^Employment\s+\.", "percent", None),
        ("economic.retail_sales_growth_pct", "retail_sales_growth", r"^Retail sales\s+\.", "percent", None),
        ("economic.exchange_rate.cad_per_usd", "cad_per_usd", r"^Exchange rate \(US cents/Canadian dollar\)", "CAD_per_USD", "us_cents_to_cad_per_usd"),
    ]
    for variable_id, slug, pattern, unit, transform in rows:
        _, line = _find_line(table, pattern)
        values = numbers(line)[:4]
        if len(values) != 4:
            raise HistoricalExtractionError(f"Budget 2026 {slug} did not contain four Ministry values")
        output += _forecast_values(
            years,
            values,
            2026,
            variable_id=variable_id,
            source_series_id=f"budget2026_{slug}",
            unit=unit,
            evidence=line,
            table="Table 1.5.1",
            transform=transform,
        )

    material = _section(text, r"Table A5 Material Assumptions|a le A5 Material Assumptions")
    for variable_id, slug, pattern, unit in [
        ("economic.cpi.all_items_yoy_pct", "cpi_growth", r"Consumer Price Index .*?([0-9.]+%\s+[0-9.]+%\s+[0-9.]+%\s+[0-9.]+%)", "percent"),
        ("economic.housing_starts.annual_units", "housing_starts", r"Housing starts \(units\).*?([0-9,]+\s+[0-9,]+\s+[0-9,]+\s+[0-9,]+)", "dwelling_units"),
        ("economic.population.growth_yoy_pct", "population_growth", r"Population .*?(-?[0-9.]+%\s+-?[0-9.]+%\s+-?[0-9.]+%\s+-?[0-9.]+%)", "percent"),
    ]:
        match = re.search(pattern, material, re.IGNORECASE | re.DOTALL)
        if not match:
            raise HistoricalExtractionError(f"Budget 2026 material assumptions missing {slug}")
        values = numbers(match.group(1))[:4]
        output += _forecast_values(
            years,
            values,
            2026,
            variable_id=variable_id,
            source_series_id=f"budget2026_{slug}",
            unit=unit,
            evidence=match.group(0),
            table="Table A5 Material Assumptions",
        )

    # The forecast narrative remains the cleanest stable source for unemployment.
    unemployment = re.search(
        r"unemployment rate is expected to average\s*([0-9.]+)\s*per cent in 2026 and\s*([0-9.]+)\s*per cent in 2027",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if unemployment:
        output += _forecast_values(
            [2026, 2027],
            [float(unemployment.group(1)), float(unemployment.group(2))],
            2026,
            variable_id="economic.unemployment_rate_pct",
            source_series_id="budget2026_unemployment_rate",
            unit="percent",
            evidence=unemployment.group(0),
            table="Economic outlook narrative",
        )
    return output


HYDRO_SERVICE_ROWS: tuple[tuple[str, str, str, str], ...] = (
    ("demand.electricity_growth_pct_per_year", "domestic_sales_growth", r"^Domestic Sales Load Growth \(%\)", "percent_per_year"),
    ("demand.utility.electricity_forecast_gwh", "domestic_sales_volume", r"^Domestic Sales Volume \(GWh\)", "GWh"),
    ("utility.system_exports_gwh", "system_exports", r"^System Exports Volume \(GWh\)", "GWh"),
    ("utility.line_loss_and_system_use_gwh", "line_loss", r"^Line Loss and System Use \(GWh\)", "GWh"),
    ("utility.total_load_and_exports_gwh", "total_load_exports", r"^Total Load and System Exports \(GWh\)", "GWh"),
    ("utility.domestic_generation_gwh", "hydro_generation", r"^Hydro Generation \(GWh\)", "GWh"),
    ("utility.system_imports_gwh", "system_imports", r"^System Imports \(GWh\)", "GWh"),
    ("utility.independent_power_purchases_gwh", "independent_power_purchases", r"^(Independent Power Producers|Long-term Purchases)", "GWh"),
    ("utility.thermal_generation_gwh", "thermal_generation", r"^Thermal Generation", "GWh"),
    ("utility.water_inflows_pct_of_average", "water_inflows", r"^Total System Water Inflows", "percent"),
    ("commodity.electricity.midc_usd_per_mwh", "midc_price", r"^(Average )?Mid-C Price", "USD_per_MWh"),
    ("commodity.natural_gas.sumas_usd_per_mmbtu", "sumas_gas", r"^(Average )?Natural Gas Price at Sumas", "USD_per_MMBtu"),
    ("financial.short_term_interest_rate_assumption_pct", "short_interest", r"^(Canadian )?Short-Term Interest Rate", "percent"),
    ("financial.long_term_interest_rate_assumption_pct", "long_interest", r"^(Canadian )?Long-Term Interest Rate", "percent"),
)


def _hydro_forecast_section(text: str) -> str:
    normalized = normalize_lines(text)
    starts = list(re.finditer(r"Key Forecast Assumptions, Risks and Sensitivities", normalized, re.IGNORECASE))
    if not starts:
        raise HistoricalExtractionError("Missing BC Hydro forecast-assumptions section")
    start = starts[-1].start()
    tail = normalized[start:]
    end = re.search(
        r"\nSensitivity Analysis|\nKey Forecast Sensitivities|\nCapital Expenditures by Year",
        tail[100:],
        re.IGNORECASE,
    )
    return tail[: 100 + end.start()] if end else tail


def parse_bchydro_service_plan(text: str, edition_start_year: int) -> list[HistoricalValue]:
    section = _hydro_forecast_section(text)
    # A service plan contains current-year forecast plus three plan years.
    years: list[int] = []
    for line in section.splitlines()[:30]:
        fiscal = re.findall(r"(20\d{2})/(\d{2})", line)
        if len(fiscal) >= 3:
            years = [int(start) + 1 for start, _ in fiscal]
            break
    if len(years) < 3:
        raise HistoricalExtractionError("BC Hydro service-plan fiscal-year header not found")
    expected = len(years)
    output: list[HistoricalValue] = []
    for variable_id, slug, pattern, unit in HYDRO_SERVICE_ROWS:
        try:
            values, evidence = _row_values(section, pattern, expected)
        except HistoricalExtractionError:
            # Two recurring labels can wrap onto a second line. Search a compact copy.
            compact = re.sub(r"\n+", " ", section)
            match = re.search(pattern + r".*?((?:\(?-?[0-9,$.]+\)?\s+){" + str(expected - 1) + r"}\(?-?[0-9,$.]+\)?)", compact, re.IGNORECASE)
            if not match:
                continue
            values = numbers(match.group(1))
            evidence = match.group(0)
        if len(values) != expected:
            continue
        for year, value in zip(years, values):
            output.append(
                HistoricalValue(
                    variable_id=variable_id,
                    source_series_id=f"bchydro_service_{edition_start_year}_{slug}_{year}",
                    value=value,
                    target_year=year,
                    unit=unit,
                    record_kind="forecast",
                    period_basis="fiscal_year_bc",
                    scenario="BC Hydro Service Plan",
                    entity_id="bc_hydro",
                    evidence_text=evidence,
                    evidence_table="Key Forecast Assumptions, Risks and Sensitivities",
                    metadata={"service_plan_start_year": edition_start_year},
                )
            )
    # Capex sometimes sits outside the assumptions table and appears several times. Use the
    # first consolidated row immediately before the assumptions section.
    prefix = normalize_lines(text).split("Key Forecast Assumptions, Risks and Sensitivities", 1)[0]
    capex_matches = list(re.finditer(r"^\s*Capital Expenditures\s+(.+)$", prefix, re.IGNORECASE | re.MULTILINE))
    if capex_matches:
        values = numbers(capex_matches[-1].group(1))
        if len(values) >= expected:
            values = values[-expected:]
            for year, value in zip(years, values):
                output.append(
                    HistoricalValue(
                        variable_id="utility.capex_forecast_cad_millions",
                        source_series_id=f"bchydro_service_{edition_start_year}_capex_{year}",
                        value=value,
                        target_year=year,
                        unit="CAD_millions",
                        record_kind="forecast",
                        period_basis="fiscal_year_bc",
                        scenario="BC Hydro Service Plan",
                        entity_id="bc_hydro",
                        evidence_text=capex_matches[-1].group(0),
                        evidence_table="Financial Plan",
                    )
                )
    core = {item.variable_id for item in output}
    required = {
        "demand.utility.electricity_forecast_gwh",
        "utility.system_exports_gwh",
        "utility.total_load_and_exports_gwh",
        "utility.domestic_generation_gwh",
        "utility.system_imports_gwh",
    }
    missing = required - core
    if missing:
        raise HistoricalExtractionError(
            f"BC Hydro service plan {edition_start_year} missing core variables: {sorted(missing)}"
        )
    return output


def parse_bchydro_annual_report(text: str, fiscal_end_year: int) -> list[HistoricalValue]:
    text = normalize_lines(text)
    output: list[HistoricalValue] = []
    contracts = [
        ("demand.utility.electricity_sales_gwh", "domestic_sales", r"^GWh Sold \(Domestic\)", "GWh"),
        ("utility.capex_actual_cad_millions", "capital_expenditures", r"^Total Capital Expenditures", "CAD_millions"),
    ]
    for variable_id, slug, pattern, unit in contracts:
        _, line = _find_line(text, pattern)
        values = numbers(line)
        if len(values) < 2:
            raise HistoricalExtractionError(
                f"BC Hydro annual report {fiscal_end_year} row {slug} is ambiguous: {line!r}"
            )
        if slug == "capital_expenditures":
            plausible = [value for value in values if 500 <= value <= 20000]
            if len(plausible) < 2:
                raise HistoricalExtractionError(
                    f"BC Hydro annual report {fiscal_end_year} capex row is implausible: {line!r}"
                )
            value, prior = plausible[0], plausible[1]
        else:
            value, prior = values[0], values[1]
        output.append(
            HistoricalValue(
                variable_id=variable_id,
                source_series_id=f"bchydro_annual_{fiscal_end_year}_{slug}",
                value=value,
                target_year=fiscal_end_year,
                unit=unit,
                record_kind="observation",
                period_basis="fiscal_year_bc",
                entity_id="bc_hydro",
                evidence_text=line,
                evidence_table="Annual Service Plan Report",
                metadata={"comparison_value_prior_year": prior},
            )
        )
    return output


@dataclass(frozen=True, slots=True)
class FortisDocument:
    utility: str
    year: int
    url: str
    title: str


def discover_fortis_annual_mda(
    html: str,
    base_url: str,
    *,
    start_year: int = 2021,
    end_year: int | None = None,
) -> list[FortisDocument]:
    """Discover annual MD&A links from FortisBC's maintained investor index."""

    end_year = end_year or date.today().year
    soup = BeautifulSoup(html, "html.parser")
    output: dict[tuple[str, int], FortisDocument] = {}
    current_utility: str | None = None
    current_year: int | None = None
    for node in soup.find_all(["h2", "h3", "h4", "a"]):
        text = " ".join(node.get_text(" ", strip=True).split())
        lower = text.lower()
        if node.name == "h2":
            if "gas utility" in lower:
                current_utility = "fei"
            elif "electricity utility" in lower or "electric utility" in lower:
                current_utility = "fbc"
        if node.name in {"h3", "h4"}:
            year_match = re.search(r"(?:year end|year-end|reports?)\s*(20\d{2})", lower)
            if year_match:
                current_year = int(year_match.group(1))
        if node.name != "a" or not current_utility:
            continue
        href = node.get("href")
        if not href:
            continue
        year_match = re.search(r"20(?:2[0-9]|1[0-9])", text + " " + href)
        year = int(year_match.group(0)) if year_match else current_year
        if year is None or year < start_year or year > end_year:
            continue
        # Annual MD&A links are usually labelled MD&A under a Year end heading, or have
        # q4/year-end tokens in their file name. Exclude financial statements and AIFs.
        href_lower = href.lower()
        is_mda = "md&a" in lower or "mda" in href_lower or "md-a" in href_lower or "mdanda" in href_lower
        annual = bool(re.search(r"(?:q4|ye-|year)", href_lower)) or "year ended" in lower
        if is_mda and annual and "aif" not in href_lower and "fs" not in href_lower:
            output[(current_utility, year)] = FortisDocument(
                utility=current_utility,
                year=year,
                url=urljoin(base_url, href),
                title=text or f"{current_utility.upper()} annual MD&A {year}",
            )
    documents = sorted(output.values(), key=lambda item: (item.utility, item.year))
    expected_keys = {
        (utility, year)
        for utility in ("fei", "fbc")
        for year in range(start_year, end_year + 1)
    }
    # The current year's annual filing does not exist until after year end.
    if end_year == date.today().year:
        expected_keys -= {(utility, end_year) for utility in ("fei", "fbc")}
    found_keys = {(item.utility, item.year) for item in documents}
    missing = sorted(expected_keys - found_keys)
    if missing:
        raise HistoricalExtractionError(f"FortisBC annual MD&A discovery missing: {missing}")
    return documents


def parse_fortis_annual_mda(text: str, utility: str, year: int) -> list[HistoricalValue]:
    text = normalize_lines(text)
    compact = re.sub(r"\s+", " ", text)
    entity = "fortisbc_energy" if utility == "fei" else "fortisbc_electric"
    sales_variable = (
        "demand.utility.natural_gas_sales_pj"
        if utility == "fei"
        else "demand.utility.electricity_sales_gwh"
    )
    sales_unit = "PJ" if utility == "fei" else "GWh"
    sales_label = (
        r"Gas sales \(petajoules\)"
        if utility == "fei"
        else r"Electricity sales \((?:GWh|gigawatt hours)\)"
    )
    # Annual filings commonly present Q4 current/prior/variance followed by annual
    # current/prior/variance. Capture the annual current value, not the Q4 value.
    sales = re.search(
        sales_label + r"\s+((?:\(?-?[0-9,.]+\)?\s+){5}\(?-?[0-9,.]+\)?)",
        compact,
        re.IGNORECASE,
    )
    if not sales:
        raise HistoricalExtractionError(f"Fortis {utility} {year} missing annual sales row")
    sales_values = numbers(sales.group(1))
    if len(sales_values) < 6:
        raise HistoricalExtractionError(f"Fortis {utility} {year} annual sales row is ambiguous")
    annual_sales = sales_values[3]
    output = [
        HistoricalValue(
            variable_id=sales_variable,
            source_series_id=f"fortis_{utility}_{year}_annual_sales",
            value=annual_sales,
            target_year=year,
            unit=sales_unit,
            record_kind="observation",
            entity_id=entity,
            evidence_text=sales.group(0),
            evidence_table="Results of Operations",
        )
    ]

    cost_label = r"Cost of natural gas" if utility == "fei" else r"Power purchase costs"
    cost_variable = (
        "utility.natural_gas_cost_cad_millions"
        if utility == "fei"
        else "utility.power_purchase_cost_cad_millions"
    )
    cost = re.search(
        cost_label + r"\s+((?:\(?-?[0-9,.]+\)?\s+){5}\(?-?[0-9,.]+\)?)",
        compact,
        re.IGNORECASE,
    )
    if cost:
        cost_values = numbers(cost.group(1))
        if len(cost_values) >= 6:
            output.append(
                HistoricalValue(
                    variable_id=cost_variable,
                    source_series_id=f"fortis_{utility}_{year}_annual_cost",
                    value=cost_values[3],
                    target_year=year,
                    unit="CAD_millions",
                    record_kind="observation",
                    entity_id=entity,
                    evidence_text=cost.group(0),
                    evidence_table="Results of Operations",
                )
            )

    # Annual MD&A documents normally disclose both the current-year actual capital
    # program and the next-year forecast. Keep actuals and forecasts as separate
    # records and preserve the filing year as the forecast vintage.
    capex_patterns = [
        (
            re.compile(
                r"The\s+(20\d{2})\s+(?:projected|forecast)\s+capital expenditures"
                r"\s+(?:are|were)\s+(?:approximately\s+)?\$?([0-9,]+)\s+million",
                re.IGNORECASE,
            ),
            "forecast",
        ),
        (
            re.compile(
                r"The\s+(20\d{2})\s+(?:annual\s+)?capital expenditures"
                r"\s+(?:are|were)\s+(?:approximately\s+)?\$?([0-9,]+)\s+million",
                re.IGNORECASE,
            ),
            "observation",
        ),
    ]
    capex_by_kind_year: dict[tuple[str, int], tuple[float, str]] = {}
    for pattern, kind in capex_patterns:
        for match in pattern.finditer(compact):
            target_year = int(match.group(1))
            value = parse_number(match.group(2))
            if not 10 <= value <= 20_000:
                raise HistoricalExtractionError(
                    f"Fortis {utility} {year} capital expenditure is implausible: {value}"
                )
            # Later statements generally carry the final or updated disclosure.
            capex_by_kind_year[(kind, target_year)] = (value, match.group(0))

    for (kind, target_year), (value, evidence) in sorted(capex_by_kind_year.items()):
        variable_id = (
            "utility.capex_forecast_cad_millions"
            if kind == "forecast"
            else "utility.capex_actual_cad_millions"
        )
        output.append(
            HistoricalValue(
                variable_id=variable_id,
                source_series_id=f"fortis_{utility}_{year}_capex_{kind}_{target_year}",
                value=value,
                target_year=target_year,
                unit="CAD_millions",
                record_kind=kind,
                period_basis="annual",
                entity_id=entity,
                evidence_text=evidence,
                evidence_table="Capital expenditures",
                metadata={
                    **({"forecast_vintage_year": year} if kind == "forecast" else {}),
                    "evidence_type": (
                        "utility_forecast" if kind == "forecast" else "observed_result"
                    ),
                    "decision_context": "FortisBC utility capital planning and delivery",
                },
            )
        )

    # Prefer explicit current-period statements over transition sentences. This avoids
    # reading the old value from phrases such as "increased from X to Y".
    financial_patterns: list[tuple[str, bool]] = [
        (
            rf"Both\s+{year}\s+and\s+{year - 1}\s+net earnings are based on an "
            r"allowed (?:return on (?:common )?equity(?: \(ROE\))?|ROE) of\s*"
            r"([0-9.]+)\s*(?:per cent|percent|%).{0,250}?deemed (?:common )?equity"
            r".{0,100}?([0-9.]+)\s*(?:per cent|percent|%)",
            False,
        ),
        (
            r"deemed (?:common )?equity component of (?:total )?capital structure"
            r".{0,100}?and allowed ROE will change from\s*[0-9.]+\s*(?:per cent|percent|%)"
            r"\s+and\s*[0-9.]+\s*(?:per cent|percent|%)\s+to\s*([0-9.]+)"
            r"\s*(?:per cent|percent|%)\s+and\s*([0-9.]+)\s*(?:per cent|percent|%)",
            True,
        ),
        (
            r"deemed (?:common )?equity component of (?:total )?capital structure"
            r".{0,120}?from\s*[0-9.]+\s*(?:per cent|percent|%)\s+to\s*"
            r"([0-9.]+)\s*(?:per cent|percent|%).{0,180}?allowed (?:return on "
            r"(?:common )?equity(?: \(ROE\))?|ROE).{0,100}?from\s*[0-9.]+"
            r"\s*(?:per cent|percent|%)\s+to\s*([0-9.]+)\s*(?:per cent|percent|%)",
            True,
        ),
        (
            r"allowed (?:return on (?:common )?equity(?: \(ROE\))?|ROE) "
            r"(?:of|was|is)\s*([0-9.]+)\s*(?:per cent|percent|%).{0,350}?deemed "
            r"(?:common )?equity.{0,150}?([0-9.]+)\s*(?:per cent|percent|%)",
            False,
        ),
    ]
    financial = None
    reverse = False
    for pattern, is_reverse in financial_patterns:
        financial = re.search(pattern, compact, re.IGNORECASE)
        if financial:
            reverse = is_reverse
            break
    if financial:
        first, second = float(financial.group(1)), float(financial.group(2))
        roe, equity = (second, first) if reverse else (first, second)
        if not (0 < roe < 30 and 0 < equity < 100):
            raise HistoricalExtractionError(
                f"Fortis {utility} {year} regulatory parameters failed plausibility checks"
            )
        for variable_id, slug, value in [
            ("financial.allowed_roe_pct", "allowed_roe", roe),
            ("financial.deemed_equity_pct", "deemed_equity", equity),
        ]:
            output.append(
                HistoricalValue(
                    variable_id=variable_id,
                    source_series_id=f"fortis_{utility}_{year}_{slug}",
                    value=value,
                    target_year=None,
                    unit="percent",
                    record_kind="model_parameter",
                    period_basis="non_temporal",
                    entity_id=entity,
                    evidence_text=financial.group(0),
                    evidence_table="Regulation",
                    metadata={
                        "effective_year": year,
                        "approval_status": "approved",
                        "parameter_scope": slug,
                        "time_basis": "non_temporal_parameter",
                        "decision_context": "BCUC-approved utility financial parameters",
                        "evidence_type": "approved_regulatory_assumption",
                    },
                )
            )

    customer = re.search(
        r"serving approximately\s+([0-9,]+)\s+.{0,100}?customers",
        compact,
        re.IGNORECASE,
    )
    if customer:
        customer_count = parse_number(customer.group(1))
        if not 10_000 <= customer_count <= 2_000_000:
            raise HistoricalExtractionError(
                f"Fortis {utility} {year} customer count is implausible: {customer_count}"
            )
        output.append(
            HistoricalValue(
                variable_id="utility.customer_count",
                source_series_id=f"fortis_{utility}_{year}_customer_count",
                value=customer_count,
                target_year=year,
                unit="customers",
                record_kind="observation",
                entity_id=entity,
                evidence_text=customer.group(0),
                evidence_table="Corporate overview",
            )
        )

    # Pension discount rates are accounting assumptions, not social or project
    # discount rates. Keep them non-temporal and explicitly scoped.
    pension = re.search(
        r"assumed discount rate.{0,350}?(?:is|was)\s*([0-9.]+)\s*(?:per cent|percent|%)",
        compact,
        re.IGNORECASE,
    )
    if pension:
        pension_rate = float(pension.group(1))
        if not 0 < pension_rate < 20:
            raise HistoricalExtractionError(
                f"Fortis {utility} {year} pension discount rate is implausible"
            )
        output.append(
            HistoricalValue(
                variable_id="financial.pension_discount_rate_pct",
                source_series_id=f"fortis_{utility}_{year}_pension_discount_rate",
                value=pension_rate,
                target_year=None,
                unit="percent",
                record_kind="model_parameter",
                period_basis="non_temporal",
                entity_id=entity,
                evidence_text=pension.group(0),
                evidence_table="Employee future benefits",
                metadata={
                    "effective_year": year,
                    "parameter_scope": "pension benefit obligation measurement",
                    "not_social_or_project_discount_rate": True,
                    "time_basis": "non_temporal_parameter",
                    "decision_context": "utility pension accounting assumptions",
                    "evidence_type": "private_sector_guidance",
                },
            )
        )

    rate_base_pattern = re.compile(
        r"(20\d{2}) forecast average rate base of (?:approximately )?\$?([0-9,]+)\s*million",
        re.IGNORECASE,
    )
    rate_base_by_year: dict[int, tuple[float, str]] = {}
    for match in rate_base_pattern.finditer(compact):
        target_year = int(match.group(1))
        value = parse_number(match.group(2))
        if not 100 <= value <= 50_000:
            raise HistoricalExtractionError(
                f"Fortis {utility} {year} rate-base forecast is implausible: {value}"
            )
        # Later mentions generally represent filed updates or final approvals.
        rate_base_by_year[target_year] = (value, match.group(0))
    for target_year, (value, evidence) in sorted(rate_base_by_year.items()):
        output.append(
            HistoricalValue(
                variable_id="utility.rate_base_cad_millions",
                source_series_id=f"fortis_{utility}_{year}_rate_base_forecast_{target_year}",
                value=value,
                target_year=target_year,
                unit="CAD_millions",
                record_kind="forecast",
                period_basis="annual",
                entity_id=entity,
                evidence_text=evidence,
                evidence_table="Regulation",
                metadata={
                    "forecast_vintage_year": year,
                    "evidence_type": "utility_forecast",
                    "decision_context": "FortisBC regulatory and financial planning",
                },
            )
        )

    return output
