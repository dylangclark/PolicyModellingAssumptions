from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath
from urllib.parse import urlparse

from .base import SourceAdapter
from .tabular_utils import csv_rows, find_column, norm, number, zip_csv_members
from ..models import CollectionResult, Record


class ICBCVehiclePopulationAdapter(SourceAdapter):
    """Collect annual B.C. BEV/PHEV stock from an ICBC CSV export.

    The adapter intentionally does not scrape Tableau internals. It consumes a direct
    CSV/ZIP export URL recorded in configuration and fails closed when the export schema,
    aggregation scope, or propulsion labels change.
    """

    def collect(self, full_refresh: bool = False) -> CollectionResult:
        url = self.source["download_url"]
        if not url or "REPLACE_WITH" in url:
            raise ValueError("ICBC source requires a verified direct CSV or ZIP export URL")
        response = self.http.request_bytes(self.source_id, "GET", url, label="vehicle-population")
        result = CollectionResult(self.source_id, artifacts=[response.artifact])
        path_suffix = PurePosixPath(urlparse(url).path).suffix.lower()
        is_zip = path_suffix == ".zip" or response.content[:4] == b"PK\x03\x04"
        payloads = (
            zip_csv_members(response.content)
            if is_zip
            else [("vehicle_population.csv", response.content)]
        )
        rows: list[dict[str, str]] = []
        for _, payload in payloads:
            rows.extend(csv_rows(payload, self.source.get("encoding", "utf-8-sig")))
        result.records.extend(self.parse_rows(rows, response.artifact.document_id))
        return result

    def parse_rows(self, rows: list[dict[str, str]], document_id: str) -> list[Record]:
        if not rows:
            raise ValueError("ICBC export contains no rows")
        headers = list(rows[0])
        cols = self.source.get("columns", {})
        year_col = find_column(headers, cols.get("year", ["Year", "Registration Year", "Data Year"]))
        count_col = find_column(headers, cols.get("count", ["Vehicle Count", "Vehicles", "Count", "Number of Vehicles"]))
        fuel_col = find_column(headers, cols.get("fuel", ["Fuel Type", "Power Source", "Fuel"]))
        geo_col = find_column(headers, cols.get("geography", ["Province", "Region", "Geography"]), required=False)
        vehicle_class_col = find_column(headers, cols.get("vehicle_class", ["Vehicle Class", "Vehicle Type", "Body Style"]), required=False)
        if self.source.get("require_geography_column", True) and not geo_col:
            raise ValueError("ICBC export is missing the required geography column")
        if self.source.get("allowed_vehicle_class_values") and not vehicle_class_col:
            raise ValueError("ICBC export is missing the required vehicle-class column")

        allowed_geo = {norm(v) for v in self.source.get("allowed_geography_values", ["British Columbia", "BC", "All", "Grand Total"])}
        preferred_geo = [norm(v) for v in self.source.get("preferred_geography_values", [])]
        selected_geo = None
        if geo_col:
            available_geo = {norm(row.get(geo_col)) for row in rows}
            candidates = preferred_geo or list(allowed_geo)
            selected_geo = next((value for value in candidates if value in available_geo), None)
            if selected_geo is None:
                raise ValueError(
                    f"ICBC export contains no approved geography scope; found {sorted(available_geo)!r}"
                )
        allowed_classes = {norm(v) for v in self.source.get("allowed_vehicle_class_values", [])}
        classes = self.source.get("powertrain_labels", {})
        bev_labels = {norm(v) for v in classes.get("bev", ["Battery Electric", "Electric", "BEV"])}
        phev_labels = {norm(v) for v in classes.get("phev", ["Plug-in Hybrid", "PHEV", "Plug In Hybrid"])}

        totals: dict[tuple[int, str], float] = defaultdict(float)
        seen_detail_keys: set[tuple[str, ...]] = set()
        for row in rows:
            if geo_col and norm(row.get(geo_col)) != selected_geo:
                continue
            if vehicle_class_col and allowed_classes and norm(row.get(vehicle_class_col)) not in allowed_classes:
                continue
            try:
                year = int(str(row.get(year_col, "")).strip()[:4])
            except ValueError:
                continue
            value = number(row.get(count_col))
            if value is None or value < 0:
                continue
            fuel = norm(row.get(fuel_col))
            kind = "bev" if fuel in bev_labels else "phev" if fuel in phev_labels else None
            if not kind:
                continue
            # Reject duplicate exported detail rows rather than silently double counting.
            detail_key = tuple(str(row.get(h, "")) for h in headers)
            if detail_key in seen_detail_keys:
                raise ValueError("ICBC export contains exact duplicate rows")
            seen_detail_keys.add(detail_key)
            totals[(year, kind)] += value

        if not totals:
            raise ValueError("ICBC export produced no BEV/PHEV observations")
        minimum_years = int(self.source.get("minimum_years", 1))
        for kind in ("bev", "phev"):
            years = sorted(year for year, candidate in totals if candidate == kind)
            if len(years) < minimum_years:
                raise ValueError(
                    f"ICBC export has only {len(years)} year(s) for {kind}; minimum is {minimum_years}"
                )
        records: list[Record] = []
        series = {s["kind"]: s for s in self.source.get("series", [])}
        previous: dict[str, tuple[int, float]] = {}
        for (year, kind), value in sorted(totals.items()):
            cfg = series[kind]
            records.append(
                Record(
                    variable_id=cfg["variable_id"],
                    source_id=self.source_id,
                    source_series_id=cfg["source_series_id"],
                    value=value,
                    unit_original="vehicles",
                    unit_canonical="vehicles",
                    reference_period_start=f"{year}-01-01",
                    reference_period_end=f"{year}-12-31",
                    period_basis="annual",
                    geography_id="CA-BC",
                    document_id=document_id,
                    extraction_method="csv",
                    metadata={
                        "powertrain": kind,
                        "scope": self.source.get("scope_note"),
                        "evidence_type": "observed",
                        "assumption_owner": "ICBC",
                        "source_status": "published_open_data",
                        "selected_geography_scope": selected_geo,
                    },
                )
            )
            prior = previous.get(kind)
            growth_variable = cfg.get("growth_variable_id")
            if growth_variable and prior and prior[0] == year - 1 and prior[1] != 0:
                records.append(
                    Record(
                        variable_id=growth_variable,
                        source_id=self.source_id,
                        source_series_id=f"{cfg['source_series_id']}_growth_yoy",
                        value=(value / prior[1] - 1.0) * 100.0,
                        unit_original="percent",
                        unit_canonical="percent",
                        reference_period_start=f"{year}-01-01",
                        reference_period_end=f"{year}-12-31",
                        period_basis="annual",
                        geography_id="CA-BC",
                        document_id=document_id,
                        extraction_method="derived_from_csv",
                        metadata={
                            "powertrain": kind,
                            "scope": self.source.get("scope_note"),
                            "formula": "(stock_t / stock_t_minus_1 - 1) * 100",
                            "evidence_type": "derived",
                            "assumption_owner": "ICBC",
                            "source_status": "derived_from_published_open_data",
                            "selected_geography_scope": selected_geo,
                        },
                    )
                )
            previous[kind] = (year, value)
        return records
