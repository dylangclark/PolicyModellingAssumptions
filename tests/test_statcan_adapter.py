from types import SimpleNamespace

import pytest

from bc_assumptions.adapters.statcan_wds import StatisticsCanadaWDSAdapter
from bc_assumptions.http import AcquisitionError


METADATA = {
    "productId": "99999999",
    "frequencyCode": 6,
    "dimension": [
        {
            "dimensionPositionId": 1,
            "dimensionNameEn": "Geography",
            "member": [
                {"memberId": 1, "memberNameEn": "Canada", "terminated": 0},
                {"memberId": 2, "memberNameEn": "British Columbia", "terminated": 0},
            ],
        },
        {
            "dimensionPositionId": 2,
            "dimensionNameEn": "Measure",
            "member": [
                {"memberId": 1, "memberNameEn": "Employment", "terminated": 0},
                {"memberId": 2, "memberNameEn": "Labour force", "terminated": 0},
            ],
        },
    ],
}


def test_resolve_coordinate():
    coordinate = StatisticsCanadaWDSAdapter.resolve_coordinate(
        METADATA,
        [
            {"dimension": "^Geography$", "member": "^British Columbia$"},
            {"dimension": "^Measure$", "member": "^Employment$"},
        ],
    )
    assert coordinate == "2.1.0.0.0.0.0.0.0.0"


def test_resolve_coordinate_fails_loudly_on_changed_member():
    with pytest.raises(AcquisitionError, match="matched 0 members"):
        StatisticsCanadaWDSAdapter.resolve_coordinate(
            METADATA,
            [
                {"dimension": "^Geography$", "member": "^British Columbia$"},
                {"dimension": "^Measure$", "member": "^Jobs$"},
            ],
        )


def test_normalize_points_applies_statcan_scalar(db, tmp_path):
    http = SimpleNamespace(raw_dir=tmp_path / "data/raw")
    source = {"id": "statcan"}
    adapter = StatisticsCanadaWDSAdapter(source, {}, db, http)
    points = adapter._normalize_points(
        [
            {
                "refPerRaw": "2025-01-01",
                "value": 2.9,
                "scalarFactorCode": 3,
                "frequencyCode": 6,
                "statusCode": 0,
                "symbolCode": 0,
                "releaseTime": "2025-02-07T08:30",
            }
        ],
        dataset={"product_id": 14100287, "table_number": "14-10-0287-01"},
        vector_id=123,
        coordinate="1.1.0.0.0.0.0.0.0.0",
        document_id="doc_test",
    )
    assert points[0]["value"] == 2900
    assert points[0]["reference_period_end"] == "2025-01-31"
    assert points[0]["publication_date"] == "2025-02-07"
