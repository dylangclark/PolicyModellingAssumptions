from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .base import SourceAdapter
from ..models import CollectionResult, Record


class BankOfCanadaValetAdapter(SourceAdapter):
    def collect(self, full_refresh: bool = False) -> CollectionResult:
        series = self.source.get("series", [])
        if not series:
            return CollectionResult(
                self.source_id, warnings=["No Bank of Canada series configured"]
            )

        start_date = self._start_date(series, full_refresh)
        series_ids = [row["source_series_id"] for row in series]
        endpoint = f"{self.source['base_url'].rstrip('/')}/observations/{','.join(series_ids)}/json"
        response = self.http.request_json(
            self.source_id,
            "GET",
            endpoint,
            label="observations",
            params={"start_date": start_date},
        )
        artifact = response.artifact
        data = response.data
        observations = data.get("observations", []) if isinstance(data, dict) else []
        details = data.get("seriesDetail", {}) if isinstance(data, dict) else {}
        config_by_id = {row["source_series_id"]: row for row in series}
        records: list[Record] = []

        for observation in observations:
            period = observation.get("d")
            if not period:
                continue
            for series_id, config in config_by_id.items():
                cell = observation.get(series_id)
                if not isinstance(cell, dict) or cell.get("v") in {None, ""}:
                    continue
                try:
                    value = float(str(cell["v"]).replace(",", ""))
                except ValueError:
                    continue
                variable = self.variables[config["variable_id"]]
                records.append(
                    Record(
                        variable_id=config["variable_id"],
                        source_id=self.source_id,
                        source_series_id=series_id,
                        value=value,
                        unit_original=config["unit_original"],
                        unit_canonical=config["unit_canonical"],
                        reference_period_start=period,
                        reference_period_end=period,
                        period_basis="daily",
                        geography_id=variable.get("geography_id"),
                        document_id=artifact.document_id,
                        extraction_method="api",
                        metadata={
                            "series_label": details.get(series_id, {}).get("label"),
                            "description": details.get(series_id, {}).get("description"),
                        },
                    )
                )
        return CollectionResult(self.source_id, artifacts=[artifact], records=records)

    def _start_date(self, series: list[dict[str, Any]], full_refresh: bool) -> str:
        configured = str(self.source.get("start_date", "2000-01-01"))
        if full_refresh:
            return configured
        latest_dates: list[date] = []
        for row in series:
            latest = self.db.latest_reference_start(self.source_id, row["source_series_id"])
            if not latest:
                return configured
            latest_dates.append(date.fromisoformat(latest[:10]))
        lookback = int(self.source.get("lookback_days", 45))
        return (min(latest_dates) - timedelta(days=lookback)).isoformat()
