from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Iterator

from .config import RegistryConfig
from .db import RegistryDB


@dataclass(frozen=True, slots=True)
class CoverageRequirement:
    """One configured source-series/variable pair that must exist and be current."""

    source_id: str
    source_series_id: str
    variable_id: str
    stale_after_days: int | None


def _positive_int(value: Any) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


def _stale_after_days(*rows: dict[str, Any]) -> int | None:
    for row in rows:
        value = _positive_int(row.get("stale_after_days"))
        if value is not None:
            return value
    return None


def _coverage_is_required(*rows: dict[str, Any]) -> bool:
    """Resolve output coverage requirements from most to least specific."""

    for row in rows:
        if "required" in row:
            return bool(row["required"])
    return True


def iter_coverage_requirements(source: dict[str, Any]) -> Iterator[CoverageRequirement]:
    """Yield the records an enabled source is expected to maintain.

    The source-series identifiers mirror the identifiers produced by each adapter. This
    keeps release checks configuration-driven instead of embedding source-specific rules.
    """

    source_id = source["id"]
    for series in source.get("series", []):
        source_series_id = str(series["source_series_id"])
        outputs = series.get("outputs") or ([series] if series.get("variable_id") else [])
        for output in outputs:
            if not _coverage_is_required(output, series, source):
                continue
            yield CoverageRequirement(
                source_id=source_id,
                source_series_id=source_series_id,
                variable_id=output["variable_id"],
                stale_after_days=_stale_after_days(output, series, source),
            )

    for dataset in source.get("datasets", []):
        series_rows = dataset.get("series") or [
            {
                "source_series_key": dataset["dataset_id"],
                "outputs": dataset.get("outputs", []),
            }
        ]
        for series in series_rows:
            source_series_key = series.get("source_series_key") or dataset["dataset_id"]
            source_series_id = f"{dataset['product_id']}:{source_series_key}"
            outputs = series.get("outputs") or dataset.get("outputs", [])
            for output in outputs:
                if not _coverage_is_required(output, series, dataset, source):
                    continue
                yield CoverageRequirement(
                    source_id=source_id,
                    source_series_id=source_series_id,
                    variable_id=output["variable_id"],
                    stale_after_days=_stale_after_days(output, series, dataset, source),
                )


def coverage_blockers_for_source(
    source: dict[str, Any],
    db: RegistryDB,
    *,
    as_of: date | None = None,
) -> list[str]:
    """Return missing or stale coverage blockers for one source."""

    as_of = as_of or date.today()
    coverage_rows = db.coverage_rows(source["id"])
    coverage = {
        (row["source_series_id"], row["variable_id"]): row
        for row in coverage_rows
    }

    coverage_by_variable: dict[str, dict[str, Any]] = {}
    for row in coverage_rows:
        variable_id = row["variable_id"]
        existing = coverage_by_variable.get(variable_id)
        if existing is None:
            coverage_by_variable[variable_id] = row
            continue

        existing_period = str(existing.get("latest_period") or "")
        candidate_period = str(row.get("latest_period") or "")
        if candidate_period > existing_period:
            coverage_by_variable[variable_id] = row

    match_mode = source.get("coverage_match", "source_series_id")
    if match_mode not in {"source_series_id", "variable_id"}:
        raise ValueError(
            f"{source['id']}: unsupported coverage_match {match_mode!r}"
        )

    blockers: list[str] = []
    for requirement in iter_coverage_requirements(source):
        label = f"{requirement.source_series_id}/{requirement.variable_id}"

        if match_mode == "variable_id":
            row = coverage_by_variable.get(requirement.variable_id)
        else:
            key = (requirement.source_series_id, requirement.variable_id)
            row = coverage.get(key)
        if row is None or not row.get("latest_period"):
            blockers.append(f"{source['id']}: missing required series {label}")
            continue
        if requirement.stale_after_days is None:
            continue
        try:
            latest_period = date.fromisoformat(str(row["latest_period"])[:10])
        except ValueError:
            blockers.append(
                f"{source['id']}: invalid latest reference period for {label}: "
                f"{row['latest_period']!r}"
            )
            continue
        age_days = (as_of - latest_period).days
        if age_days > requirement.stale_after_days:
            blockers.append(
                f"{source['id']}: stale series {label}; latest period "
                f"{latest_period.isoformat()} is {age_days} days old "
                f"(limit {requirement.stale_after_days})"
            )
    return blockers


def _parse_finished_at(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def source_is_required(source: dict[str, Any]) -> bool:
    """Resolve the release role while remaining compatible with older source files."""

    return bool(source.get("required", not source.get("optional", False)))


def release_blockers(
    config: RegistryConfig,
    db: RegistryDB,
    *,
    as_of: datetime | None = None,
) -> list[str]:
    """Evaluate whether the database is safe to publish as a complete release."""

    now = (as_of or datetime.now(UTC)).astimezone(UTC)
    blockers: list[str] = []
    for source_id, source in config.sources.items():
        if not source.get("enabled", False) or not source_is_required(source):
            continue
        latest = db.latest_run(source_id)
        if latest is None:
            blockers.append(f"{source_id}: no collection run has been recorded")
        else:
            status = latest.get("status")
            if status != "success":
                blockers.append(f"{source_id}: latest run status is {status!r}, not 'success'")
            finished_at = latest.get("finished_at")
            if not finished_at:
                blockers.append(f"{source_id}: latest run has no finished_at timestamp")
            else:
                try:
                    age_days = (now - _parse_finished_at(str(finished_at))).total_seconds() / 86400
                except ValueError:
                    blockers.append(
                        f"{source_id}: invalid latest run finished_at value {finished_at!r}"
                    )
                else:
                    limit = _positive_int(source.get("collection_stale_after_days"))
                    if limit is not None and age_days > limit:
                        blockers.append(
                            f"{source_id}: latest successful collection is "
                            f"{age_days:.1f} days old (limit {limit})"
                        )
        blockers.extend(coverage_blockers_for_source(source, db, as_of=now.date()))
    return blockers
