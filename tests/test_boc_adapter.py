from bc_assumptions.adapters.boc_valet import BankOfCanadaValetAdapter
from bc_assumptions.http import JsonResult


class FakeHttp:
    def __init__(self, artifact):
        self.artifact = artifact
        self.calls = []

    def request_json(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return JsonResult(
            artifact=self.artifact,
            data={
                "seriesDetail": {"V39079": {"label": "Target overnight rate"}},
                "observations": [
                    {"d": "2025-01-02", "V39079": {"v": "3.25"}},
                    {"d": "2025-01-03", "V39079": {"v": "3.25"}},
                ],
            },
        )


def test_boc_adapter_parses_observations(db, artifact):
    artifact.source_id = "bank"
    source = {
        "id": "bank",
        "base_url": "https://example.test/valet",
        "start_date": "2000-01-01",
        "series": [
            {
                "source_series_id": "V39079",
                "variable_id": "rate",
                "unit_original": "percent",
                "unit_canonical": "percent",
            }
        ],
    }
    variables = {"rate": {"id": "rate", "geography_id": "CA"}}
    result = BankOfCanadaValetAdapter(source, variables, db, FakeHttp(artifact)).collect()
    assert len(result.records) == 2
    assert result.records[0].value == 3.25
    assert result.records[0].document_id == artifact.document_id
    assert result.records[0].geography_id == "CA"


def test_boc_backfills_when_any_configured_series_is_new(db, artifact):
    artifact.source_id = "bank"
    variables = {
        "rate": {"id": "rate", "geography_id": "CA"},
        "fx": {"id": "fx", "geography_id": "CA"},
    }
    source = {
        "id": "bank",
        "base_url": "https://example.test/valet",
        "start_date": "2000-01-01",
        "series": [
            {
                "source_series_id": "V39079",
                "variable_id": "rate",
                "unit_original": "percent",
                "unit_canonical": "percent",
            },
            {
                "source_series_id": "FXUSDCAD",
                "variable_id": "fx",
                "unit_original": "CAD_per_USD",
                "unit_canonical": "CAD_per_USD",
            },
        ],
    }
    adapter = BankOfCanadaValetAdapter(source, variables, db, FakeHttp(artifact))
    assert adapter._start_date(source["series"], full_refresh=False) == "2000-01-01"
