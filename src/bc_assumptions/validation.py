from __future__ import annotations

from dataclasses import replace
from datetime import date
import math
from typing import Any

from .models import Record


class ValidationError(RuntimeError):
    pass


ALLOWED_RECORD_KINDS = {
    "observation",
    "forecast",
    "policy_target",
    "scenario",
    "sensitivity",
    "model_parameter",
    "cost_estimate",
    "qualitative_assumption",
}


def _date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Invalid {field_name}: {value!r}") from exc


def validate_record(
    record: Record,
    variables: dict[str, dict[str, Any]],
    rules: dict[str, Any] | None = None,
) -> Record:
    if record.variable_id not in variables:
        raise ValidationError(f"Unknown variable_id: {record.variable_id}")
    definition = variables[record.variable_id]
    if record.unit_canonical != definition["canonical_unit"]:
        raise ValidationError(
            f"Unit mismatch for {record.variable_id}: {record.unit_canonical} != "
            f"{definition['canonical_unit']}"
        )
    if record.record_kind not in ALLOWED_RECORD_KINDS:
        raise ValidationError(
            f"Unsupported record_kind {record.record_kind!r} for {record.variable_id}"
        )
    if record.value is None and record.range_low is None and record.range_high is None:
        raise ValidationError(f"No numeric value or range for {record.variable_id}")

    numeric_values = {
        "value": record.value,
        "range_low": record.range_low,
        "range_high": record.range_high,
    }
    for field_name, value in numeric_values.items():
        if value is not None and not math.isfinite(float(value)):
            raise ValidationError(f"Non-finite {field_name} for {record.variable_id}")
    if (
        record.range_low is not None
        and record.range_high is not None
        and record.range_low > record.range_high
    ):
        raise ValidationError(f"Range low exceeds range high for {record.variable_id}")

    if not record.reference_period_start or not record.reference_period_end:
        raise ValidationError(f"Missing reference period for {record.variable_id}")
    reference_start = _date(record.reference_period_start, "reference_period_start")
    reference_end = _date(record.reference_period_end, "reference_period_end")
    if reference_end < reference_start:
        raise ValidationError(f"Reference period end precedes start for {record.variable_id}")

    if bool(record.target_period_start) != bool(record.target_period_end):
        raise ValidationError(
            f"Target period must include both start and end for {record.variable_id}"
        )
    if record.target_period_start and record.target_period_end:
        target_start = _date(record.target_period_start, "target_period_start")
        target_end = _date(record.target_period_end, "target_period_end")
        if target_end < target_start:
            raise ValidationError(f"Target period end precedes start for {record.variable_id}")

    if record.record_kind != "observation" and not (record.vintage_date or record.publication_date):
        raise ValidationError(
            f"Non-observation record requires a publication or vintage date: {record.variable_id}"
        )

    flags = list(dict.fromkeys(record.quality_flags))
    status = record.validation_status
    minimum = definition.get("expected_min")
    maximum = definition.get("expected_max")
    for value in numeric_values.values():
        if value is not None and (
            (minimum is not None and value < float(minimum))
            or (maximum is not None and value > float(maximum))
        ):
            flags.append("outside_expected_range")
            if status == "validated":
                status = "needs_review"
            break

    quality_rules = (rules or {}).get("quality_flags", {})
    if not record.publication_date and "missing_publication_date" in quality_rules:
        flags.append("missing_publication_date")

    return replace(
        record,
        validation_status=status,
        quality_flags=list(dict.fromkeys(flags)),
    )
