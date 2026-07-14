from bc_assumptions.adapters.nrcan_neud import NRCanNEUDAdapter
from bc_assumptions.http import BytesResult
from bc_assumptions.models import Artifact


class FakeHttp:
    def __init__(self, content, artifact):
        self.content = content
        self.artifact = artifact

    def request_bytes(self, *args, **kwargs):
        return BytesResult(self.artifact, self.content)


def test_nrcan_neud_adapter(db):
    html = b'''<html><table>
    <tr><th>Measure</th><th>2021</th><th>2022</th><th>2023</th></tr>
    <tr><td>Heat Pump</td><td>128.6</td><td>168.3</td><td>212.2</td></tr>
    <tr><td>Electric</td><td>819.8</td><td>824.7</td><td>828.0</td></tr>
    <tr><td>Heat Pump</td><td>5.9</td><td>7.5</td><td>9.2</td></tr>
    </table></html>'''
    artifact = Artifact("nrcan", "https://example.test/table", "nrcan/table.html", "text/html", "2026-07-14T00:00:00Z", "b"*64, len(html))
    source = {"id":"nrcan","tables":[{"table_id":"t21","url":"https://example.test/table","geography_id":"CA-BC","series":[
        {"source_series_id":"hp_stock","variable_id":"hp_stock","row_pattern":"^Heat Pump$","occurrence":1,"multiplier":1000,"unit_original":"thousand_systems","unit_canonical":"systems"},
        {"source_series_id":"hp_share","variable_id":"hp_share","row_pattern":"^Heat Pump$","occurrence":2,"unit_original":"percent","unit_canonical":"percent"},
    ]}]}
    variables = {"hp_stock":{"geography_id":"CA-BC"},"hp_share":{"geography_id":"CA-BC"}}
    result = NRCanNEUDAdapter(source, variables, db, FakeHttp(html, artifact)).collect()
    assert len(result.records) == 6
    assert next(r.value for r in result.records if r.variable_id == "hp_stock" and r.reference_period_start == "2023-01-01") == 212200.0
    assert next(r.value for r in result.records if r.variable_id == "hp_share" and r.reference_period_start == "2023-01-01") == 9.2
