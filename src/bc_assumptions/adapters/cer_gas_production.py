from __future__ import annotations

import calendar
from datetime import date, datetime

from .base import SourceAdapter
from .tabular_utils import csv_rows, find_column, number
from ..models import CollectionResult, Record


class CERGasProductionAdapter(SourceAdapter):
    """Collect monthly provincial marketable natural-gas production from CER CSV."""

    def collect(self, full_refresh: bool = False) -> CollectionResult:
        response = self.http.request_bytes(self.source_id, "GET", self.source["download_url"], label="provincial-gas-production")
        result = CollectionResult(self.source_id, artifacts=[response.artifact])
        result.records.extend(self.parse_rows(csv_rows(response.content), response.artifact.document_id))
        return result

    def parse_rows(self, rows: list[dict[str, str]], document_id: str) -> list[Record]:
        if not rows:
            raise ValueError("CER gas production CSV contains no rows")
        headers = list(rows[0])
        province_col = find_column(headers, ["Province", "Region"])
        date_col = find_column(headers, ["Date", "Month", "REF_DATE"])
        value_col = find_column(headers, ["Marketable Gas Production (10^3 m^3)", "Marketable Production (10^3 m3)", "Value"])
        unit_col = find_column(headers, ["Unit", "UOM"], required=False)
        cfg = self.source["series"][0]
        records: list[Record] = []
        for row in rows:
            if str(row.get(province_col, "")).strip().lower() not in {"british columbia", "bc"}:
                continue
            raw_date = str(row.get(date_col, "")).strip()
            month = None
            for fmt in (
                "%Y-%m",
                "%Y-%m-%d",
                "%Y/%m",
                "%m/%d/%Y",
                "%b-%y",
                "%B %Y",
            ):
                try:
                    parsed = datetime.strptime(raw_date, fmt)
                    month = date(parsed.year, parsed.month, 1)
                    break
                except ValueError:
                    pass
            value = number(row.get(value_col))
            if month is None or value is None:
                continue

            unit = str(row.get(unit_col) or "").strip() if unit_col else ""
            if unit.lower() == "thousand cubic metres per day":
                value *= calendar.monthrange(month.year, month.month)[1]
                unit_original = "e3m3_per_day"
            else:
                unit_original = unit or "e3m3"

            records.append(Record(
                variable_id=cfg["variable_id"], source_id=self.source_id,
                source_series_id=cfg["source_series_id"], value=value,
                unit_original=unit_original,
                unit_canonical="e3m3", reference_period_start=month.isoformat(),
                reference_period_end=date(month.year, month.month, calendar.monthrange(month.year, month.month)[1]).isoformat(),
                period_basis="monthly", geography_id="CA-BC", document_id=document_id,
                extraction_method="csv", metadata={"measure": "marketable_natural_gas_production"},
            ))
        if not records:
            raise ValueError("CER gas production CSV produced no B.C. observations")
        return records
