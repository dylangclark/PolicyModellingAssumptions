from io import BytesIO

from openpyxl import Workbook

from bc_assumptions.adapters.world_bank_pink_sheet import WorldBankPinkSheetAdapter
from bc_assumptions.http import BytesResult
from bc_assumptions.models import Artifact


class FakeHttp:
    def __init__(self, content, artifact):
        self.content = content
        self.artifact = artifact

    def request_bytes(self, *args, **kwargs):
        return BytesResult(self.artifact, self.content)


def workbook_bytes():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Monthly Prices"
    sheet.append(["World Bank commodity prices"])
    sheet.append(["Date", "Copper", "LNG, Japan"])
    sheet.append(["2025M01", 9000, 12.5])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def modern_workbook_bytes():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Monthly Prices"
    sheet.append(["World Bank commodity prices"])
    sheet.append([None, "Copper", "Liquefied natural gas, Japan"])
    sheet.append([None, "($/mt)", "($/mmbtu)"])
    sheet.append(["2025M01", 9000, 12.5])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def test_world_bank_adapter(db, tmp_path):
    artifact = Artifact(
        source_id="wb",
        source_url="https://example.test/pink.xlsx",
        local_path="wb/aa/pink.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        retrieved_at="2026-07-13T12:00:00Z",
        sha256="b" * 64,
        size_bytes=100,
    )
    source = {
        "id": "wb",
        "download_url": "https://example.test/pink.xlsx",
        "start_date": "2000-01-01",
        "sheet_regex": "^Monthly Prices$",
        "series": [
            {
                "source_series_id": "Copper",
                "aliases": ["^Copper$"],
                "variable_id": "copper",
                "unit_original": "USD_per_metric_tonne",
                "unit_canonical": "USD_per_metric_tonne",
            },
            {
                "source_series_id": "LNG, Japan",
                "aliases": ["^LNG,? Japan$"],
                "variable_id": "lng_proxy",
                "unit_original": "USD_per_MMBtu",
                "unit_canonical": "USD_per_MMBtu",
                "quality_flags": ["proxy_series", "not_jkm"],
            },
        ],
    }
    variables = {
        "copper": {"geography_id": "GLOBAL"},
        "lng_proxy": {"geography_id": "JP"},
    }
    result = WorldBankPinkSheetAdapter(
        source, variables, db, FakeHttp(workbook_bytes(), artifact)
    ).collect()
    assert len(result.records) == 2
    assert {row.value for row in result.records} == {9000.0, 12.5}
    lng = next(row for row in result.records if row.variable_id == "lng_proxy")
    assert lng.quality_flags == ["proxy_series", "not_jkm"]
    assert lng.metadata["is_jkm"] is False
    assert lng.vintage_date is None


def test_world_bank_adapter_accepts_blank_period_header(db):
    artifact = Artifact(
        source_id="wb",
        source_url="https://example.test/pink.xlsx",
        local_path="wb/aa/pink.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        retrieved_at="2026-07-13T12:00:00Z",
        sha256="c" * 64,
        size_bytes=100,
    )
    source = {
        "id": "wb",
        "download_url": "https://example.test/pink.xlsx",
        "start_date": "2000-01-01",
        "sheet_regex": "^Monthly Prices$",
        "series": [
            {
                "source_series_id": "Copper",
                "aliases": ["^Copper$"],
                "variable_id": "copper",
                "unit_original": "USD_per_metric_tonne",
                "unit_canonical": "USD_per_metric_tonne",
            },
            {
                "source_series_id": "LNG_Japan_proxy",
                "aliases": ["^Liquefied natural gas,? Japan$"],
                "variable_id": "lng_proxy",
                "unit_original": "USD_per_MMBtu",
                "unit_canonical": "USD_per_MMBtu",
            },
        ],
    }
    variables = {
        "copper": {"geography_id": "GLOBAL"},
        "lng_proxy": {"geography_id": "JP"},
    }

    result = WorldBankPinkSheetAdapter(
        source, variables, db, FakeHttp(modern_workbook_bytes(), artifact)
    ).collect()

    assert len(result.records) == 2
    assert {row.value for row in result.records} == {9000.0, 12.5}
