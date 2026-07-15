from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Iterable


FORECAST_KINDS = {"forecast"}


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _match_key(row: dict[str, Any], *, forecast: bool) -> tuple[Any, ...] | None:
    if forecast:
        start = row.get("target_period_start")
        end = row.get("target_period_end")
    else:
        start = row.get("reference_period_start")
        end = row.get("reference_period_end")
    if not start or not end:
        return None
    return (
        row.get("variable_id"),
        row.get("unit_canonical"),
        row.get("geography_id"),
        row.get("entity_id"),
        start,
        end,
    )


def build_forecast_performance(
    records: Iterable[dict[str, Any]],
    *,
    source_authority: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Match forecast vintages to later observed values using exact period semantics.

    Matching is deliberately strict: variable, canonical unit, geography, entity and
    target/reference dates must all agree. This prevents a provincial observation from
    being used to score a utility-service-area forecast, or a quarterly value from being
    matched to an annual forecast. When more than one observed source is available, the
    lowest authority-tier number is preferred and the candidate count is retained.
    """

    rows = list(records)
    authority = source_authority or {}
    observed: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("record_kind") != "observation" or row.get("value") is None:
            continue
        key = _match_key(row, forecast=False)
        if key is not None:
            observed[key].append(row)

    output: list[dict[str, Any]] = []
    for forecast in rows:
        if forecast.get("record_kind") not in FORECAST_KINDS or forecast.get("value") is None:
            continue
        key = _match_key(forecast, forecast=True)
        if key is None or key not in observed:
            continue
        candidates = sorted(
            observed[key],
            key=lambda row: (
                int(authority.get(str(row.get("source_id")), 99)),
                str(row.get("source_id") or ""),
                str(row.get("record_id") or ""),
            ),
        )
        actual = candidates[0]
        forecast_value = float(forecast["value"])
        actual_value = float(actual["value"])
        signed_error = forecast_value - actual_value
        publication = _date(forecast.get("publication_date") or forecast.get("vintage_date"))
        target_start = _date(forecast.get("target_period_start"))
        lead_days = (target_start - publication).days if publication and target_start else None
        output.append(
            {
                "forecast_record_id": forecast.get("record_id"),
                "actual_record_id": actual.get("record_id"),
                "variable_id": forecast.get("variable_id"),
                "unit_canonical": forecast.get("unit_canonical"),
                "geography_id": forecast.get("geography_id"),
                "entity_id": forecast.get("entity_id"),
                "target_period_start": forecast.get("target_period_start"),
                "target_period_end": forecast.get("target_period_end"),
                "forecast_source_id": forecast.get("source_id"),
                "actual_source_id": actual.get("source_id"),
                "forecast_vintage_date": forecast.get("vintage_date")
                or forecast.get("publication_date"),
                "scenario_original": forecast.get("scenario_original"),
                "forecast_value": forecast_value,
                "actual_value": actual_value,
                "signed_error": signed_error,
                "absolute_error": abs(signed_error),
                "absolute_percentage_error": (
                    abs(signed_error / actual_value) * 100.0 if actual_value != 0 else None
                ),
                "forecast_lead_days": lead_days,
                "actual_candidate_count": len(candidates),
                "match_method": "exact_variable_unit_geography_entity_period",
            }
        )
    return sorted(
        output,
        key=lambda row: (
            str(row["variable_id"]),
            str(row["target_period_start"]),
            str(row["forecast_vintage_date"]),
            str(row["forecast_source_id"]),
        ),
    )
