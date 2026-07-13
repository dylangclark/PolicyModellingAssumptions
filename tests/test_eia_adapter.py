from bc_assumptions.adapters.eia_v2 import EIAOpenDataAdapter


class DummyHttp:
    pass


def test_eia_monthly_row(db):
    adapter = EIAOpenDataAdapter(
        {"id": "eia"},
        {"gas": {"geography_id": "US"}},
        db,
        DummyHttp(),
    )
    row = adapter._row_to_record(
        {"period": "2025-01", "value": "3.50", "units": "$/MMBtu"},
        {
            "source_series_id": "RNGWHHD",
            "variable_id": "gas",
            "unit_original": "dollars_per_mmbtu",
            "unit_canonical": "USD_per_MMBtu",
            "frequency": "monthly",
        },
        "doc_test",
    )
    assert row is not None
    assert row.reference_period_start == "2025-01-01"
    assert row.reference_period_end == "2025-01-31"
    assert row.value == 3.5
