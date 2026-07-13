from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import json
import re
from typing import Any, Iterable

from .base import SourceAdapter
from ..http import AcquisitionError
from ..models import Artifact, CollectionResult, Record
from ..transforms import FREQUENCY_NAMES, SCALAR_MULTIPLIERS, calculate_yoy, period_end


class StatisticsCanadaWDSAdapter(SourceAdapter):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.cache_path = self.http.raw_dir.parent / "cache" / "statcan_vectors.json"
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache = self._load_cache()

    def collect(self, full_refresh: bool = False) -> CollectionResult:
        result = CollectionResult(self.source_id)
        for dataset in self.source.get("datasets", []):
            metadata_response = self.http.request_json(
                self.source_id,
                "POST",
                f"{self.source['base_url'].rstrip('/')}/getCubeMetadata",
                label=f"metadata-{dataset['product_id']}",
                json_body=[{"productId": int(dataset["product_id"])}],
            )
            result.artifacts.append(metadata_response.artifact)
            metadata = self._unwrap_one(metadata_response.data)
            if str(metadata.get("archiveStatusCode", "2")) not in {"2", "CURRENT"}:
                result.warnings.append(
                    f"Statistics Canada product {dataset['product_id']} is not marked current"
                )

            series_configs = dataset.get("series") or [
                {
                    "source_series_key": dataset["dataset_id"],
                    "selectors": [],
                    "outputs": dataset.get("outputs", []),
                }
            ]
            for series_config in series_configs:
                selectors = [
                    *dataset.get("common_selectors", []),
                    *dataset.get("selectors", []),
                    *series_config.get("selectors", []),
                ]
                coordinate = self.resolve_coordinate(metadata, selectors)
                vector_id, series_info, info_artifact = self._resolve_vector(
                    dataset, coordinate, metadata
                )
                if info_artifact:
                    result.artifacts.append(info_artifact)
                source_series_id = (
                    f"{dataset['product_id']}:{series_config.get('source_series_key', vector_id)}"
                )
                start_date = self._start_date(
                    dataset,
                    source_series_id,
                    int(series_info.get("frequencyCode") or metadata.get("frequencyCode") or 0),
                    full_refresh,
                )
                points_response = self.http.request_json(
                    self.source_id,
                    "GET",
                    f"{self.source['base_url'].rstrip('/')}/getDataFromVectorByReferencePeriodRange",
                    label=f"vector-{vector_id}",
                    params={
                        "vectorIds": f'"{vector_id}"',
                        "startRefPeriod": start_date,
                        "endReferencePeriod": date.today().isoformat(),
                    },
                )
                result.artifacts.append(points_response.artifact)
                point_object = self._unwrap_one(points_response.data)
                raw_points = point_object.get("vectorDataPoint", [])
                base_points = self._normalize_points(
                    raw_points,
                    dataset=dataset,
                    vector_id=vector_id,
                    coordinate=coordinate,
                    document_id=points_response.artifact.document_id,
                )
                for output in series_config.get("outputs", dataset.get("outputs", [])):
                    transformed = (
                        calculate_yoy(base_points)
                        if output.get("transform") == "yoy_pct"
                        else deepcopy(base_points)
                    )
                    result.records.extend(
                        self._to_records(
                            transformed,
                            dataset,
                            output,
                            source_series_id,
                            vector_id,
                            coordinate,
                        )
                    )
        self._save_cache()
        return result

    def inspect_product(self, product_id: int) -> tuple[dict[str, Any], Artifact]:
        response = self.http.request_json(
            self.source_id,
            "POST",
            f"{self.source['base_url'].rstrip('/')}/getCubeMetadata",
            label=f"metadata-{product_id}",
            json_body=[{"productId": int(product_id)}],
        )
        return self._unwrap_one(response.data), response.artifact

    @staticmethod
    def _response_objects(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, dict) and data.get("status") == "SUCCESS":
            obj = data.get("object")
            if isinstance(obj, list):
                return [item for item in obj if isinstance(item, dict)]
            if isinstance(obj, dict):
                return [obj]
        if isinstance(data, list):
            objects: list[dict[str, Any]] = []
            for item in data:
                if isinstance(item, dict) and item.get("status") == "SUCCESS":
                    obj = item.get("object")
                    if isinstance(obj, dict):
                        objects.append(obj)
                    elif isinstance(obj, list):
                        objects.extend(value for value in obj if isinstance(value, dict))
                elif isinstance(item, dict) and "responseStatusCode" in item:
                    objects.append(item)
            return objects
        return []

    @classmethod
    def _unwrap_one(cls, data: Any) -> dict[str, Any]:
        objects = cls._response_objects(data)
        if not objects:
            raise AcquisitionError(
                f"Statistics Canada returned no successful object: {str(data)[:300]}"
            )
        return objects[0]

    @staticmethod
    def resolve_coordinate(metadata: dict[str, Any], selectors: list[dict[str, str]]) -> str:
        dimensions = metadata.get("dimension") or metadata.get("dimensions") or []
        if not dimensions:
            raise AcquisitionError("Statistics Canada metadata contains no dimensions")
        selected: dict[int, int] = {}
        used_selectors: set[int] = set()

        for position, dimension in enumerate(dimensions, start=1):
            dimension_position = int(dimension.get("dimensionPositionId", position))
            dimension_name = str(dimension.get("dimensionNameEn") or dimension.get("name") or "")
            matching_selectors = [
                (index, selector)
                for index, selector in enumerate(selectors)
                if re.search(selector["dimension"], dimension_name, flags=re.IGNORECASE)
            ]
            if len(matching_selectors) > 1:
                raise AcquisitionError(
                    f"Multiple selectors match Statistics Canada dimension {dimension_name}: {matching_selectors}"
                )
            members = [
                member
                for member in (dimension.get("member") or dimension.get("members") or [])
                if int(member.get("terminated", 0) or 0) == 0
            ]
            if matching_selectors:
                selector_index, selector = matching_selectors[0]
                used_selectors.add(selector_index)
                matches = [
                    member
                    for member in members
                    if re.search(
                        selector["member"],
                        str(member.get("memberNameEn") or member.get("name") or ""),
                        flags=re.IGNORECASE,
                    )
                ]
                if len(matches) != 1:
                    choices = [member.get("memberNameEn") for member in members[:40]]
                    raise AcquisitionError(
                        f"Selector {selector['member']!r} matched {len(matches)} members in "
                        f"{dimension_name!r}. Available examples: {choices}"
                    )
                selected[dimension_position] = int(matches[0]["memberId"])
            elif len(members) == 1:
                selected[dimension_position] = int(members[0]["memberId"])
            else:
                choices = [member.get("memberNameEn") for member in members[:40]]
                raise AcquisitionError(
                    f"No selector supplied for multi-member dimension {dimension_name!r}. "
                    f"Available examples: {choices}"
                )

        unused = [
            selectors[index] for index in range(len(selectors)) if index not in used_selectors
        ]
        if unused:
            names = [dimension.get("dimensionNameEn") for dimension in dimensions]
            raise AcquisitionError(
                f"Selectors did not match a dimension: {unused}. Available dimensions: {names}"
            )
        positions = [0] * 10
        for position, member_id in selected.items():
            if position > 10:
                raise AcquisitionError("Statistics Canada coordinate exceeds ten dimensions")
            positions[position - 1] = member_id
        return ".".join(str(value) for value in positions)

    def _resolve_vector(
        self, dataset: dict[str, Any], coordinate: str, metadata: dict[str, Any]
    ) -> tuple[int, dict[str, Any], Artifact | None]:
        key = f"{dataset['product_id']}:{coordinate}"
        issue_date = metadata.get("issueDate") or metadata.get("releaseTime")
        cached = self.cache.get(key)
        if cached and cached.get("issue_date") == issue_date:
            return int(cached["vector_id"]), cached.get("series_info", {}), None
        response = self.http.request_json(
            self.source_id,
            "POST",
            f"{self.source['base_url'].rstrip('/')}/getSeriesInfoFromCubePidCoord",
            label=f"series-{dataset['product_id']}",
            json_body=[{"productId": int(dataset["product_id"]), "coordinate": coordinate}],
        )
        info = self._unwrap_one(response.data)
        vector_id = int(info["vectorId"])
        self.cache[key] = {
            "vector_id": vector_id,
            "coordinate": coordinate,
            "issue_date": issue_date,
            "series_info": info,
        }
        return vector_id, info, response.artifact

    def _start_date(
        self,
        dataset: dict[str, Any],
        source_series_id: str,
        frequency_code: int,
        full_refresh: bool,
    ) -> str:
        configured = str(dataset.get("start_date", "2000-01-01"))
        if full_refresh:
            return configured
        latest = self.db.latest_reference_start(self.source_id, source_series_id)
        if not latest:
            return configured
        revision_years = self.source.get("revision_lookback_years")
        if revision_years is not None:
            days = int(float(revision_years) * 366)
            return (date.fromisoformat(latest[:10]) - timedelta(days=days)).isoformat()
        periods = int(self.source.get("lookback_periods", 18))
        days_per_period = {
            1: 1,
            2: 7,
            4: 14,
            6: 31,
            7: 62,
            9: 93,
            11: 183,
            12: 366,
            13: 732,
            14: 1098,
            15: 1464,
            16: 1830,
            17: 3660,
        }.get(frequency_code, 31)
        return (
            date.fromisoformat(latest[:10]) - timedelta(days=periods * days_per_period)
        ).isoformat()

    def _normalize_points(
        self,
        rows: Iterable[dict[str, Any]],
        *,
        dataset: dict[str, Any],
        vector_id: int,
        coordinate: str,
        document_id: str,
    ) -> list[dict[str, Any]]:
        points: list[dict[str, Any]] = []
        for row in rows:
            raw_value = row.get("value")
            ref = row.get("refPerRaw") or row.get("refPer")
            if raw_value in {None, "", ".."} or not ref:
                continue
            try:
                scalar_code = int(row.get("scalarFactorCode", 0) or 0)
                value = float(raw_value) * SCALAR_MULTIPLIERS.get(scalar_code, 1)
            except (TypeError, ValueError):
                continue
            start = date.fromisoformat(str(ref)[:10])
            frequency_code = int(row.get("frequencyCode", 0) or 0)
            ref_end = row.get("refPerRaw2") or row.get("refPer2")
            end = (
                date.fromisoformat(str(ref_end)[:10])
                if ref_end
                else period_end(start, frequency_code)
            )
            flags: list[str] = []
            if int(row.get("statusCode", 0) or 0) != 0:
                flags.append("statcan_nonzero_status")
            if int(row.get("symbolCode", 0) or 0) != 0:
                flags.append("statcan_nonzero_symbol")
            release = str(row.get("releaseTime", ""))[:10] or None
            points.append(
                {
                    "value": value,
                    "reference_period_start": start.isoformat(),
                    "reference_period_end": end.isoformat(),
                    "period_basis": FREQUENCY_NAMES.get(frequency_code, str(frequency_code)),
                    "publication_date": release,
                    "vintage_date": release,
                    "document_id": document_id,
                    "quality_flags": flags,
                    "metadata": {
                        "product_id": int(dataset["product_id"]),
                        "table_number": dataset.get("table_number"),
                        "vector_id": vector_id,
                        "coordinate": coordinate,
                        "frequency_code": frequency_code,
                        "scalar_factor_code": scalar_code,
                        "decimals": row.get("decimals"),
                        "status_code": row.get("statusCode"),
                        "symbol_code": row.get("symbolCode"),
                    },
                }
            )
        return points

    def _to_records(
        self,
        rows: list[dict[str, Any]],
        dataset: dict[str, Any],
        output: dict[str, Any],
        source_series_id: str,
        vector_id: int,
        coordinate: str,
    ) -> list[Record]:
        records: list[Record] = []
        multiplier = float(output.get("multiplier", 1))
        variable = self.variables[output["variable_id"]]
        for row in rows:
            value = float(row["value"]) * multiplier
            records.append(
                Record(
                    variable_id=output["variable_id"],
                    source_id=self.source_id,
                    source_series_id=source_series_id,
                    value=value,
                    unit_original=output["unit_original"],
                    unit_canonical=output["unit_canonical"],
                    reference_period_start=row["reference_period_start"],
                    reference_period_end=row["reference_period_end"],
                    period_basis=row["period_basis"],
                    publication_date=row.get("publication_date"),
                    vintage_date=row.get("vintage_date"),
                    geography_id=variable.get("geography_id"),
                    document_id=row.get("document_id"),
                    extraction_method="api",
                    quality_flags=row.get("quality_flags", []),
                    metadata={
                        **row.get("metadata", {}),
                        **output.get("metadata", {}),
                        "transform": output.get("transform", "level"),
                        "resolved_vector_id": vector_id,
                        "resolved_coordinate": coordinate,
                        "replaces_product_ids": dataset.get("replaces_product_ids", []),
                    },
                )
            )
        return records

    def _load_cache(self) -> dict[str, Any]:
        if not self.cache_path.exists():
            return {}
        try:
            value = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_cache(self) -> None:
        temporary = self.cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.cache, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.cache_path)
