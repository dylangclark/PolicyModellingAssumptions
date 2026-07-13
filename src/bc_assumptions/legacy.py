from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from pathlib import Path
import re


@dataclass(slots=True)
class LegacyRow:
    assumption_class: str
    variable_label: str
    source_label: str
    period_raw: str
    scenario_raw: str
    value_raw: str
    unit_raw: str
    notes: str
    value: float | None = None
    range_low: float | None = None
    range_high: float | None = None
    value_type: str = "text"
    migration_status: str = "needs_source_provenance"
    provenance_note: str = "Legacy seed only; exact document, vintage, page and table must be verified before publication."


def _cells(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip().replace("\\|", "|") for cell in stripped.split("|")]


def parse_value(raw: str) -> tuple[float | None, float | None, float | None, str]:
    text = raw.strip().replace(",", "")
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        return float(text), None, None, "number"
    match = re.fullmatch(r"([-+]?\d+(?:\.\d+)?)\s*[-–]\s*([-+]?\d+(?:\.\d+)?)", text)
    if match:
        low, high = float(match.group(1)), float(match.group(2))
        return None, low, high, "range"
    return None, None, None, "text"


def parse_markdown_table(text: str) -> list[LegacyRow]:
    lines = [line for line in text.splitlines() if line.strip().startswith("|")]
    if len(lines) < 3:
        raise ValueError("No Markdown table found")
    header = [cell.lower() for cell in _cells(lines[0])]
    expected = [
        "assumption class",
        "variable",
        "source",
        "year",
        "scenario",
        "value",
        "units",
        "notes",
    ]
    if header[:8] != expected:
        raise ValueError(f"Unexpected legacy header: {header}")
    rows: list[LegacyRow] = []
    for line in lines[2:]:
        cells = _cells(line)
        if len(cells) < 8:
            continue
        value, low, high, value_type = parse_value(cells[5])
        rows.append(
            LegacyRow(
                assumption_class=cells[0],
                variable_label=cells[1],
                source_label=cells[2],
                period_raw=cells[3],
                scenario_raw=cells[4],
                value_raw=cells[5],
                unit_raw=cells[6],
                notes=cells[7],
                value=value,
                range_low=low,
                range_high=high,
                value_type=value_type,
            )
        )
    return rows


def migrate_legacy(input_path: Path, output_path: Path) -> list[LegacyRow]:
    rows = parse_markdown_table(input_path.read_text(encoding="utf-8-sig"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list(asdict(rows[0]).keys()) if rows else list(LegacyRow.__annotations__)
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    return rows
