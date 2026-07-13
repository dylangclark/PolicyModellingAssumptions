from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def stable_hash(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(slots=True)
class Artifact:
    source_id: str
    source_url: str
    local_path: str
    content_type: str | None
    retrieved_at: str
    sha256: str
    size_bytes: int
    request_method: str = "GET"
    request_metadata: dict[str, Any] = field(default_factory=dict)
    response_headers: dict[str, str] = field(default_factory=dict)

    @property
    def document_id(self) -> str:
        identity = {
            "source_id": self.source_id,
            "source_url": self.source_url,
            "sha256": self.sha256,
            "request_method": self.request_method.upper(),
            "request_metadata": self.request_metadata,
        }
        return f"doc_{stable_hash(identity)[:24]}"


@dataclass(slots=True)
class SourcePoint:
    period_start: str
    period_end: str
    value: float | None
    source_row_key: str
    publication_date: str | None = None
    source_status: str | None = None
    quality_flags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Record:
    variable_id: str
    source_id: str
    source_series_id: str
    value: float | None
    unit_original: str
    unit_canonical: str
    reference_period_start: str
    reference_period_end: str
    record_kind: str = "observation"
    geography_id: str | None = None
    entity_id: str | None = None
    range_low: float | None = None
    range_high: float | None = None
    target_period_start: str | None = None
    target_period_end: str | None = None
    period_basis: str | None = None
    publication_date: str | None = None
    vintage_date: str | None = None
    scenario_original: str | None = None
    scenario_family: str | None = None
    statistic_type: str | None = "point_estimate"
    currency: str | None = None
    price_base_year: int | None = None
    real_or_nominal: str | None = None
    document_id: str | None = None
    evidence_page: str | None = None
    evidence_table: str | None = None
    evidence_text: str | None = None
    extraction_method: str = "api"
    validation_status: str = "validated"
    quality_flags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    record_id: str = field(default_factory=lambda: f"rec_{uuid4().hex}")

    def natural_key(self) -> dict[str, Any]:
        # Observations can be revised by the publisher. They retain the same natural key
        # and create a new registry revision. Forecasts and assumptions retain each vintage.
        vintage_key = None
        if self.record_kind != "observation":
            vintage_key = self.vintage_date or self.publication_date
        return {
            "variable_id": self.variable_id,
            "source_id": self.source_id,
            "source_series_id": self.source_series_id,
            "record_kind": self.record_kind,
            "geography_id": self.geography_id,
            "entity_id": self.entity_id,
            "reference_period_start": self.reference_period_start,
            "reference_period_end": self.reference_period_end,
            "target_period_start": self.target_period_start,
            "target_period_end": self.target_period_end,
            "scenario_original": self.scenario_original,
            "statistic_type": self.statistic_type,
            "vintage_key": vintage_key,
        }

    def revision_payload(self) -> dict[str, Any]:
        # Metadata and retrieval timestamps are intentionally excluded. A revised value,
        # unit, status, range, or modelling basis creates a new version; a re-download does not.
        return {
            "value": self.value,
            "range_low": self.range_low,
            "range_high": self.range_high,
            "unit_original": self.unit_original,
            "unit_canonical": self.unit_canonical,
            "period_basis": self.period_basis,
            "scenario_family": self.scenario_family,
            "currency": self.currency,
            "price_base_year": self.price_base_year,
            "real_or_nominal": self.real_or_nominal,
            "validation_status": self.validation_status,
            "quality_flags": sorted(set(self.quality_flags)),
            "evidence_page": self.evidence_page if self.record_kind != "observation" else None,
            "evidence_table": self.evidence_table if self.record_kind != "observation" else None,
            "evidence_text": self.evidence_text if self.record_kind != "observation" else None,
        }

    @property
    def natural_key_hash(self) -> str:
        return stable_hash(self.natural_key())

    @property
    def payload_hash(self) -> str:
        return stable_hash(self.revision_payload())

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["natural_key_hash"] = self.natural_key_hash
        value["payload_hash"] = self.payload_hash
        return value


@dataclass(slots=True)
class CollectionResult:
    source_id: str = ""
    artifacts: list[Artifact] = field(default_factory=list)
    records: list[Record] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped_reason: str | None = None


@dataclass(slots=True)
class UpsertResult:
    action: str
    record_id: str


@dataclass(slots=True)
class RunSummary:
    run_id: str
    source_id: str
    status: str
    records_seen: int = 0
    records_inserted: int = 0
    records_revised: int = 0
    records_unchanged: int = 0
    records_rejected: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
