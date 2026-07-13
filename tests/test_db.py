from __future__ import annotations

from dataclasses import replace

from bc_assumptions.models import Record


def test_record_versioning(db):
    variables = {
        "x": {
            "id": "x",
            "class": "Economic",
            "name": "Test variable",
            "canonical_unit": "percent",
        }
    }
    sources = {
        "test_source": {
            "id": "test_source",
            "name": "Test source",
            "publisher": "Test publisher",
            "adapter": "test",
            "enabled": True,
        }
    }
    db.sync_config(variables, sources)
    first = Record(
        variable_id="x",
        source_id="test_source",
        source_series_id="series",
        value=1.0,
        unit_original="percent",
        unit_canonical="percent",
        reference_period_start="2025-01-01",
        reference_period_end="2025-12-31",
    )
    assert db.upsert_record(first).action == "inserted"
    assert db.upsert_record(replace(first, record_id="rec_other")).action == "unchanged"
    revised = replace(first, record_id="rec_revised", value=1.5)
    assert db.upsert_record(revised).action == "revised"

    rows = db.query(
        "SELECT value, is_current, supersedes_record_id FROM records ORDER BY valid_from"
    )
    assert len(rows) == 2
    assert [row["is_current"] for row in rows] == [0, 1]
    assert rows[1]["supersedes_record_id"] == first.record_id
    assert rows[1]["value"] == 1.5
