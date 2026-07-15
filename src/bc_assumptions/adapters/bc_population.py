from __future__ import annotations

from collections import defaultdict
import csv
from datetime import date
from io import StringIO
from typing import Any

from .base import SourceAdapter
from .tabular_utils import find_column, norm, number
from ..models import CollectionResult, Record


class BCStatsPopulationAdapter(SourceAdapter):
    """Collect B.C. population estimates and projections from a BC Stats CSV.

    The adapter accepts either an explicit province-total row or a complete set of
    non-overlapping regional rows. It filters to total age and total sex before any
    aggregation and keeps estimate and projection vintages distinct.
    """

    def collect(self, full_refresh: bool = False) -> CollectionResult:
        response = self.http.request_bytes(
            self.source_id,
            "GET",
            self.source["download_url"],
            label="population-estimates-projections",
        )
        rows = list(
            csv.DictReader(StringIO(response.content.decode(self.source.get("encoding", "utf-8-sig"))))
        )
        result = CollectionResult(self.source_id, artifacts=[response.artifact])
        result.records.extend(self.parse_rows(rows, response.artifact.document_id))
        return result

    def parse_rows(self, rows: list[dict[str, Any]], document_id: str) -> list[Record]:
        if not rows:
            raise ValueError("BC Stats population CSV contains no rows")
        headers = list(rows[0])
        columns = self.source.get("columns", {})
        year_col = find_column(headers, columns.get("year", ["YEAR", "Year"]))
        value_col = find_column(
            headers,
            columns.get("population", ["POPULATION", "Population", "TOTAL_POPULATION"]),
        )
        type_col = find_column(
            headers, columns.get("type", ["TYPE", "Type", "STATUS", "Estimate/Projection"])
        )
        region_col = find_column(
            headers,
            columns.get("region", ["REGION_NAME", "Region Name", "GEOGRAPHY", "Geography"]),
        )
        region_id_col = find_column(
            headers, columns.get("region_id", ["REGION_ID", "Region ID", "GEO_CODE"]), required=False
        )
        age_col = find_column(
            headers, columns.get("age", ["AGE", "Age", "AGE_GROUP", "Age Group"]), required=False
        )
        sex_col = find_column(
            headers, columns.get("sex", ["SEX", "Sex", "GENDER", "Gender"]), required=False
        )

        total_age = {norm(value) for value in self.source.get(
            "total_age_values", ["Total", "All ages", "Total, all ages", "0-90+"]
        )}
        total_sex = {norm(value) for value in self.source.get(
            "total_sex_values", ["Total", "Both sexes", "All sexes", "All genders"]
        )}
        province_names = {norm(value) for value in self.source.get(
            "province_total_values", ["British Columbia", "BC", "Province Total"]
        )}
        estimate_labels = {norm(value) for value in self.source.get(
            "estimate_labels", ["Estimate", "Historical", "Actual"]
        )}
        projection_labels = {norm(value) for value in self.source.get(
            "projection_labels", ["Projection", "Projected", "Forecast"]
        )}

        filtered: list[tuple[int, str, str, float, str | None]] = []
        for row in rows:
            if age_col and norm(row.get(age_col)) not in total_age:
                continue
            if sex_col and norm(row.get(sex_col)) not in total_sex:
                continue
            row_type = norm(row.get(type_col))
            kind = "estimate" if row_type in estimate_labels else "projection" if row_type in projection_labels else None
            if kind is None:
                continue
            try:
                year = int(str(row.get(year_col, ""))[:4])
            except ValueError:
                continue
            value = number(row.get(value_col))
            if value is None or value < 0:
                continue
            filtered.append(
                (year, kind, str(row.get(region_col, "")).strip(), value, row.get(region_id_col) if region_id_col else None)
            )

        if not filtered:
            raise ValueError("BC Stats population CSV produced no total-age, total-sex records")

        province_rows = [row for row in filtered if norm(row[2]) in province_names]
        totals: dict[tuple[int, str], float] = {}
        aggregation_method = "province_total_row"
        region_counts: dict[tuple[int, str], int] = {}
        if province_rows:
            for year, kind, _, value, _ in province_rows:
                key = (year, kind)
                if key in totals:
                    raise ValueError(f"Duplicate B.C. province-total population row for {year}/{kind}")
                totals[key] = value
                region_counts[key] = 1
        else:
            aggregation_method = "sum_non_overlapping_regions"
            grouped: dict[tuple[int, str], dict[str, float]] = defaultdict(dict)
            for year, kind, region, value, region_id in filtered:
                key = str(region_id or region).strip()
                if not key:
                    continue
                group_key = (year, kind)
                if key in grouped[group_key]:
                    raise ValueError(f"Duplicate regional population row for {year}/{kind}/{key}")
                grouped[group_key][key] = value
            minimum_regions = int(self.source.get("minimum_region_count", 20))
            for key, values in grouped.items():
                if len(values) < minimum_regions:
                    raise ValueError(
                        f"Population aggregation for {key} has only {len(values)} regions; "
                        f"minimum is {minimum_regions}"
                    )
                totals[key] = sum(values.values())
                region_counts[key] = len(values)

        records: list[Record] = []
        previous: dict[str, tuple[int, float]] = {}
        publication_date = self.source.get("publication_date")
        vintage_date = self.source.get("vintage_date", publication_date)
        for (year, kind), value in sorted(totals.items(), key=lambda item: (item[0][1], item[0][0])):
            is_forecast = kind == "projection"
            start = date(year, 1, 1).isoformat()
            end = date(year, 12, 31).isoformat()
            metadata = {
                "evidence_type": "government_forecast" if is_forecast else "observed",
                "assumption_owner": "Government of British Columbia",
                "source_status": "published_open_data",
                "aggregation_method": aggregation_method,
                "region_count": region_counts[(year, kind)],
                "population_basis": "july_1",
                "source_row_type": kind,
            }
            records.append(
                Record(
                    variable_id="economic.population.level",
                    source_id=self.source_id,
                    source_series_id=f"bcstats_population_{kind}",
                    value=value,
                    unit_original="persons",
                    unit_canonical="persons",
                    reference_period_start=start,
                    reference_period_end=end,
                    target_period_start=start if is_forecast else None,
                    target_period_end=end if is_forecast else None,
                    record_kind="forecast" if is_forecast else "observation",
                    period_basis="annual_july_1",
                    publication_date=publication_date,
                    vintage_date=vintage_date if is_forecast else publication_date,
                    geography_id="CA-BC",
                    scenario_original=self.source.get("scenario_original", "BC Stats reference projection") if is_forecast else None,
                    scenario_family="reference" if is_forecast else None,
                    document_id=document_id,
                    extraction_method="csv",
                    metadata=metadata,
                )
            )
            prior = previous.get(kind)
            if prior and prior[0] == year - 1 and prior[1] != 0:
                records.append(
                    Record(
                        variable_id="economic.population.growth_yoy_pct",
                        source_id=self.source_id,
                        source_series_id=f"bcstats_population_{kind}_growth_yoy",
                        value=(value / prior[1] - 1.0) * 100.0,
                        unit_original="percent",
                        unit_canonical="percent",
                        reference_period_start=start,
                        reference_period_end=end,
                        target_period_start=start if is_forecast else None,
                        target_period_end=end if is_forecast else None,
                        record_kind="forecast" if is_forecast else "observation",
                        period_basis="annual_july_1",
                        publication_date=publication_date,
                        vintage_date=vintage_date if is_forecast else publication_date,
                        geography_id="CA-BC",
                        scenario_original=self.source.get("scenario_original", "BC Stats reference projection") if is_forecast else None,
                        scenario_family="reference" if is_forecast else None,
                        document_id=document_id,
                        extraction_method="derived_from_csv",
                        metadata={**metadata, "formula": "(population_t / population_t_minus_1 - 1) * 100"},
                    )
                )
            previous[kind] = (year, value)
        return records
