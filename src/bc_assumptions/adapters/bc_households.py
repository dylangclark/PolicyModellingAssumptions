from __future__ import annotations

import csv
from datetime import date
from io import StringIO
from typing import Any

from .base import SourceAdapter
from ..models import CollectionResult, Record


class BCHouseholdsAdapter(SourceAdapter):
    """Collect B.C. household estimates and projections from the BC Data Catalogue CSV."""

    def collect(self, full_refresh: bool = False) -> CollectionResult:
        result = CollectionResult(self.source_id)
        response = self.http.request_bytes(
            self.source_id,
            "GET",
            self.source["download_url"],
            label="household-estimates-projections",
        )
        result.artifacts.append(response.artifact)
        text = response.content.decode("utf-8-sig")
        rows = list(csv.DictReader(StringIO(text)))
        result.records.extend(
            self.records_from_rows(
                rows,
                source_id=self.source_id,
                document_id=response.artifact.document_id,
                geography_id=self.source.get("geography_id", "CA-BC"),
                publication_date=self.source.get("publication_date"),
                vintage_date=self.source.get("vintage_date"),
            )
        )
        return result

    @staticmethod
    def records_from_rows(
        rows: list[dict[str, Any]],
        *,
        source_id: str,
        document_id: str,
        geography_id: str = "CA-BC",
        publication_date: str | None = None,
        vintage_date: str | None = None,
    ) -> list[Record]:
        selected: list[tuple[int, str, float, dict[str, Any]]] = []
        for row in rows:
            if str(row.get("REGION_NAME", "")).strip() != "British Columbia":
                continue
            if str(row.get("REGION_ID", "")).strip() != "0":
                continue
            row_type = str(row.get("TYPE", "")).strip().lower()
            if row_type not in {"estimate", "projection"}:
                continue
            try:
                year = int(str(row["YEAR"]).strip())
                households = float(str(row["HOUSEHOLDS"]).replace(",", "").strip())
            except (KeyError, TypeError, ValueError):
                continue
            selected.append((year, row_type, households, row))

        selected.sort(key=lambda item: (item[1], item[0]))
        records: list[Record] = []
        previous: dict[str, tuple[int, float]] = {}
        for year, row_type, households, row in selected:
            is_projection = row_type == "projection"
            record_kind = "forecast" if is_projection else "observation"
            source_series_id = f"households_{row_type}"
            metadata = {
                "evidence_type": "government_forecast" if is_projection else "observed",
                "assumption_owner": "Government of British Columbia",
                "source_status": "published_open_data",
                "region_id": row.get("REGION_ID"),
                "region_type": row.get("REGION_TYPE"),
                "region_name": row.get("REGION_NAME"),
                "source_row_type": row.get("TYPE"),
                "persons_per_household": row.get("PERSONS_PER_HOUSEHOLD"),
                "population": row.get("POPULATION"),
                "household_definition": "occupied_private_dwellings",
            }
            start = date(year, 1, 1).isoformat()
            end = date(year, 12, 31).isoformat()
            records.append(
                Record(
                    variable_id="economic.households.level",
                    source_id=source_id,
                    source_series_id=source_series_id,
                    value=households,
                    unit_original="households",
                    unit_canonical="households",
                    reference_period_start=start,
                    reference_period_end=end,
                    target_period_start=start if is_projection else None,
                    target_period_end=end if is_projection else None,
                    record_kind=record_kind,
                    period_basis="annual",
                    publication_date=publication_date,
                    vintage_date=vintage_date if is_projection else publication_date,
                    geography_id=geography_id,
                    document_id=document_id,
                    extraction_method="csv",
                    metadata=metadata,
                )
            )
            prior = previous.get(row_type)
            if prior and prior[0] == year - 1 and prior[1] != 0:
                growth = (households / prior[1] - 1.0) * 100.0
                records.append(
                    Record(
                        variable_id="economic.households.growth_yoy_pct",
                        source_id=source_id,
                        source_series_id=f"households_{row_type}_growth_yoy",
                        value=growth,
                        unit_original="percent",
                        unit_canonical="percent",
                        reference_period_start=start,
                        reference_period_end=end,
                        target_period_start=start if is_projection else None,
                        target_period_end=end if is_projection else None,
                        record_kind=record_kind,
                        period_basis="annual",
                        publication_date=publication_date,
                        vintage_date=vintage_date if is_projection else publication_date,
                        geography_id=geography_id,
                        document_id=document_id,
                        extraction_method="derived_from_csv",
                        metadata={**metadata, "formula": "(value_t / value_t_minus_1_year - 1) * 100"},
                    )
                )
            previous[row_type] = (year, households)
        return records
