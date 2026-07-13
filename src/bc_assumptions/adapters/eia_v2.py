from __future__ import annotations

import calendar
from datetime import date
import os
from typing import Any

from .base import SourceAdapter
from ..models import CollectionResult, Record


class EIAOpenDataAdapter(SourceAdapter):
    def collect(self, full_refresh: bool = False) -> CollectionResult:
        key_name = self.source.get("api_key_env", "EIA_API_KEY")
        api_key = os.environ.get(key_name)
        if not api_key:
            return CollectionResult(
                self.source_id,
                skipped_reason=f"Missing environment variable {key_name}",
            )

        result = CollectionResult(self.source_id)
        for config in self.source.get("series", []):
            start = self._start_period(config, full_refresh)
            route = config["route"].lstrip("/")
            endpoint = f"{self.source['base_url'].rstrip('/')}/{route}"
            params = {
                "api_key": api_key,
                "frequency": config.get("frequency", "monthly"),
                "data[0]": "value",
                "facets[series][]": config["source_series_id"],
                "start": start,
                "sort[0][column]": "period",
                "sort[0][direction]": "asc",
                "offset": 0,
                "length": 5000,
            }
            response = self.http.request_json(
                self.source_id,
                "GET",
                endpoint,
                label=config["source_series_id"],
                params=params,
                sensitive_parameters={"api_key"},
            )
            result.artifacts.append(response.artifact)
            payload = response.data.get("response", {}) if isinstance(response.data, dict) else {}
            rows = payload.get("data", []) if isinstance(payload, dict) else []
            if payload.get("total") and int(payload["total"]) > 5000:
                result.warnings.append(
                    f"{config['source_series_id']} returned more than 5000 rows; pagination is required"
                )
            for row in rows:
                record = self._row_to_record(row, config, response.artifact.document_id)
                if record:
                    result.records.append(record)
        return result

    def _start_period(self, config: dict[str, Any], full_refresh: bool) -> str:
        configured = str(self.source.get("start_date", "2000-01"))
        if full_refresh:
            return configured
        latest = self.db.latest_reference_start(self.source_id, config["source_series_id"])
        if not latest:
            return configured
        year, month = map(int, latest[:7].split("-"))
        month -= 3
        while month <= 0:
            month += 12
            year -= 1
        return f"{year:04d}-{month:02d}"

    def _row_to_record(
        self, row: dict[str, Any], config: dict[str, Any], document_id: str
    ) -> Record | None:
        period = str(row.get("period", ""))
        raw_value = row.get("value")
        if not period or raw_value in {None, "", "NA"}:
            return None
        try:
            value = float(str(raw_value).replace(",", ""))
        except ValueError:
            return None
        if len(period) == 7:
            year, month = map(int, period.split("-"))
            start = date(year, month, 1)
            end = date(year, month, calendar.monthrange(year, month)[1])
            period_basis = "monthly"
        else:
            start = date.fromisoformat(period[:10])
            end = start
            period_basis = config.get("frequency", "daily")
        variable = self.variables[config["variable_id"]]
        return Record(
            variable_id=config["variable_id"],
            source_id=self.source_id,
            source_series_id=config["source_series_id"],
            value=value,
            unit_original=config["unit_original"],
            unit_canonical=config["unit_canonical"],
            reference_period_start=start.isoformat(),
            reference_period_end=end.isoformat(),
            period_basis=period_basis,
            geography_id=variable.get("geography_id"),
            document_id=document_id,
            extraction_method="api",
            metadata={
                "series_description": row.get("series-description"),
                "reported_units": row.get("units"),
            },
        )
