from __future__ import annotations

import calendar
import re
from collections import defaultdict
from datetime import date

from .base import SourceAdapter
from .tabular_utils import csv_rows, find_column, number, zip_csv_members
from ..models import CollectionResult, Record


class BCERProductionAdapter(SourceAdapter):
    """Aggregate BCER well/facility production CSV files to monthly B.C. totals."""

    def collect(self, full_refresh: bool = False) -> CollectionResult:
        response = self.http.request_bytes(self.source_id, "GET", self.source["download_url"], label="production-data")
        result = CollectionResult(self.source_id, artifacts=[response.artifact])
        members = zip_csv_members(response.content)
        member_regex = self.source.get("member_regex")
        if member_regex:
            members = [item for item in members if re.search(member_regex, item[0], re.IGNORECASE)]
            if not members:
                raise ValueError(f"BCER archive has no CSV member matching {member_regex!r}")
        elif len(members) != 1:
            raise ValueError(
                "BCER archive contains multiple CSV files; configure member_regex after live schema review"
            )
        rows: list[dict[str, str]] = []
        for _, payload in members:
            rows.extend(csv_rows(payload, self.source.get("encoding", "latin-1")))
        result.records.extend(self.parse_rows(rows, response.artifact.document_id))
        return result

    def parse_rows(self, rows: list[dict[str, str]], document_id: str) -> list[Record]:
        if not rows:
            raise ValueError("BCER production archive contains no rows")
        headers = list(rows[0])
        cols = self.source.get("columns", {})
        period_col = find_column(headers, cols.get("period", ["PROD_PERIOD", "Production Period", "PRODUCTION_MONTH", "YYYYMM"]))
        gas_col = find_column(headers, cols.get("gas", ["GAS_PROD_VOL", "Gas Production Volume", "GAS_M3", "Gas Volume"]))
        product_col = find_column(headers, cols.get("product", ["PRODUCT", "Product Type", "PROD_TYPE"]), required=False)
        allowed_products = {str(v).strip().lower() for v in self.source.get("allowed_product_values", ["gas", "natural gas"])}
        multiplier = float(self.source.get("multiplier_to_e3m3", 0.001))

        totals: dict[date, float] = defaultdict(float)
        seen_rows: set[tuple[str, ...]] = set()
        for row in rows:
            detail_key = tuple(str(row.get(header, "")) for header in headers)
            if detail_key in seen_rows:
                raise ValueError("BCER production archive contains exact duplicate rows")
            seen_rows.add(detail_key)
            if product_col and str(row.get(product_col, "")).strip().lower() not in allowed_products:
                continue
            token = "".join(ch for ch in str(row.get(period_col, "")) if ch.isdigit())[:6]
            if len(token) != 6:
                continue
            try:
                month = date(int(token[:4]), int(token[4:6]), 1)
            except ValueError:
                continue
            value = number(row.get(gas_col))
            if value is None or value < 0:
                continue
            totals[month] += value * multiplier
        if not totals:
            raise ValueError("BCER production archive produced no monthly gas observations")
        minimum_months = int(self.source.get("minimum_months", 1))
        if len(totals) < minimum_months:
            raise ValueError(
                f"BCER production archive has only {len(totals)} monthly observations; "
                f"minimum is {minimum_months}"
            )
        cfg = self.source["series"][0]
        return [Record(
            variable_id=cfg["variable_id"], source_id=self.source_id,
            source_series_id=cfg["source_series_id"], value=value,
            unit_original=cfg.get("unit_original", self.source.get("unit_original", "m3")),
            unit_canonical=cfg.get("unit_canonical", "e3m3"),
            reference_period_start=month.isoformat(),
            reference_period_end=date(month.year, month.month, calendar.monthrange(month.year, month.month)[1]).isoformat(),
            period_basis="monthly", geography_id="CA-BC", document_id=document_id,
            extraction_method="zip_csv", metadata={
                "aggregation": "sum_all_reported_rows",
                "measure": "gross_reported_gas_production",
                "evidence_type": "observed",
                "assumption_owner": "B.C. Energy Regulator",
                "source_status": "published_bulk_data",
            },
        ) for month, value in sorted(totals.items())]
