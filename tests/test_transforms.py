from bc_assumptions.transforms import calculate_yoy, period_end
from datetime import date


def test_calculate_yoy_uses_same_reference_date_prior_year():
    rows = [
        {"reference_period_start": "2024-03-01", "value": 100, "metadata": {}},
        {"reference_period_start": "2025-03-01", "value": 105, "metadata": {}},
    ]
    result = calculate_yoy(rows)
    assert len(result) == 1
    assert round(result[0]["value"], 8) == 5.0
    assert result[0]["metadata"]["derived_from_reference_period"] == "2024-03-01"


def test_period_end():
    assert period_end(date(2025, 2, 1), 6).isoformat() == "2025-02-28"
    assert period_end(date(2025, 4, 1), 9).isoformat() == "2025-06-30"
