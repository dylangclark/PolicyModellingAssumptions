from dataclasses import replace

import pytest

from bc_assumptions.models import Record
from bc_assumptions.validation import ValidationError, validate_record


VARIABLES = {
    "x": {
        "id": "x",
        "canonical_unit": "percent",
        "expected_min": -10,
        "expected_max": 20,
    }
}


def base_record() -> Record:
    return Record(
        variable_id="x",
        source_id="s",
        source_series_id="series",
        value=2.0,
        unit_original="percent",
        unit_canonical="percent",
        reference_period_start="2025-01-01",
        reference_period_end="2025-12-31",
    )


def test_validation_flags_missing_publication_date_without_rejecting_observation():
    record = validate_record(
        base_record(),
        VARIABLES,
        {"quality_flags": {"missing_publication_date": "warning"}},
    )
    assert record.validation_status == "validated"
    assert "missing_publication_date" in record.quality_flags


def test_validation_requires_vintage_for_non_observations():
    with pytest.raises(ValidationError, match="publication or vintage"):
        validate_record(replace(base_record(), record_kind="forecast"), VARIABLES)


def test_validation_rejects_reversed_range():
    with pytest.raises(ValidationError, match="Range low exceeds"):
        validate_record(
            replace(base_record(), value=None, range_low=5.0, range_high=2.0),
            VARIABLES,
        )
