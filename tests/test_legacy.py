from pathlib import Path

from bc_assumptions.legacy import migrate_legacy, parse_markdown_table


TEXT = """| Assumption Class | Variable | Source | Year | Scenario | Value | Units | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Cost | Capacity | Filing | 2030 | Base | 450-500 | MW | range |
| Economic | Growth | Budget | 2025 | Base | 1.8 | % | point |
| Industrial | LNG | Filing | Ongoing | Reference | Included | Qualitative | text |
"""


def test_legacy_parser_preserves_mixed_value_types(tmp_path: Path):
    rows = parse_markdown_table(TEXT)
    assert rows[0].range_low == 450
    assert rows[0].range_high == 500
    assert rows[1].value == 1.8
    assert rows[2].value_type == "text"
    input_path = tmp_path / "seed.txt"
    output_path = tmp_path / "seed.csv"
    input_path.write_text(TEXT)
    migrated = migrate_legacy(input_path, output_path)
    assert len(migrated) == 3
    assert "needs_source_provenance" in output_path.read_text()
