from bc_assumptions.adapters import bc_budget as module
from bc_assumptions.adapters.bc_budget import BCBudgetForecastAdapter
from bc_assumptions.http import BytesResult
from bc_assumptions.models import Artifact


class FakePage:
    def __init__(self, text): self.text = text
    def extract_text(self): return self.text


class FakeReader:
    def __init__(self, stream):
        self.pages = [FakePage("") for _ in range(123)]
        self.pages[13] = FakePage("economy expanded by 1.5 per cent in 2025. forecast to grow by 1.3 per cent in 2026 before increasing to 1.8 per cent in 2027")
        self.pages[121] = FakePage("overnight target rate will average 2.28 per cent in 2026 and 2.60 per cent in 2027. 10-year Government of Canada bond rate is assumed to be 3.34 per cent in 2026 and 3.49 per cent in 2027")
        self.pages[122] = FakePage("Canadian dollar will average 73.6 US cents in 2026 and 75.6 US cents in 2027")


class FakeHttp:
    def __init__(self, artifact): self.artifact = artifact
    def request_bytes(self, *args, **kwargs): return BytesResult(self.artifact, b"pdf")


def test_budget_adapter(db, monkeypatch):
    monkeypatch.setattr(module, "PdfReader", FakeReader)
    artifact = Artifact("budget", "https://example.test/b.pdf", "budget/b.pdf", "application/pdf", "2026-07-14T00:00:00Z", "c"*64, 3)
    source = {"id":"budget","documents":[{"document_id":"b2026","edition":"Budget 2026","title":"Budget","publication_date":"2026-02-17","url":"https://example.test/b.pdf","series":[
        {"source_series_id":"gdp","variable_id":"gdp","pages":[14],"target_years":[2025,2026,2027],"pattern":"economy expanded by\\s+([0-9.]+)\\s*per cent in 2025.*?forecast to grow by\\s+([0-9.]+)\\s*per cent in 2026.*?increasing to\\s+([0-9.]+)\\s*per cent in 2027","unit_original":"percent","unit_canonical":"percent","geography_id":"CA-BC"},
        {"source_series_id":"fx","variable_id":"fx","pages":[123],"target_years":[2026,2027],"pattern":"Canadian dollar will average\\s+([0-9.]+)\\s*US cents in 2026 and\\s+([0-9.]+)\\s*US cents in 2027","multiplier":0.01,"invert":True,"unit_original":"US_cents_per_CAD","unit_canonical":"CAD_per_USD","geography_id":"CA"},
    ]}]}
    variables = {"gdp":{"geography_id":"CA-BC"},"fx":{"geography_id":"CA"}}
    result = BCBudgetForecastAdapter(source, variables, db, FakeHttp(artifact)).collect()
    assert len(result.records) == 5
    fx = [r for r in result.records if r.variable_id == "fx"]
    assert round(fx[0].value, 6) == round(100/73.6, 6)
    assert all(r.record_kind == "forecast" for r in result.records)
