from __future__ import annotations

from datetime import date
import re

from bs4 import BeautifulSoup

from .base import SourceAdapter
from ..models import CollectionResult, Record


class NRCanNEUDAdapter(SourceAdapter):
    """Collect configured rows from recurring NRCan NEUD HTML tables."""

    def collect(self, full_refresh: bool = False) -> CollectionResult:
        result = CollectionResult(self.source_id)
        for table in self.source.get("tables", []):
            response = self.http.request_bytes(
                self.source_id,
                "GET",
                table["url"],
                label=table["table_id"],
            )
            result.artifacts.append(response.artifact)
            soup = BeautifulSoup(response.content, "html.parser")
            rows = self._rows(soup)
            years, year_row = self._years(rows)
            if not years:
                raise RuntimeError(f"NRCan table {table['table_id']} has no year header")
            for config in table.get("series", []):
                candidates = [
                    row
                    for row in rows[year_row + 1 :]
                    if row and re.search(config["row_pattern"], row[0], re.IGNORECASE)
                ]
                occurrence = int(config.get("occurrence", 1)) - 1
                if occurrence < 0 or occurrence >= len(candidates):
                    result.warnings.append(
                        f"NRCan {table['table_id']} series {config['source_series_id']} "
                        f"matched {len(candidates)} rows"
                    )
                    continue
                row = candidates[occurrence]
                values = [self._number(value) for value in row[1:]]
                numeric = [value for value in values if value is not None]
                if len(numeric) < len(years):
                    result.warnings.append(
                        f"NRCan {table['table_id']} row {row[0]!r} had {len(numeric)} values "
                        f"for {len(years)} years"
                    )
                for year, value in zip(years[-len(numeric) :], numeric):
                    multiplier = float(config.get("multiplier", 1.0))
                    result.records.append(
                        Record(
                            variable_id=config["variable_id"],
                            source_id=self.source_id,
                            source_series_id=config["source_series_id"],
                            value=value * multiplier,
                            unit_original=config["unit_original"],
                            unit_canonical=config["unit_canonical"],
                            reference_period_start=date(year, 1, 1).isoformat(),
                            reference_period_end=date(year, 12, 31).isoformat(),
                            period_basis="annual",
                            geography_id=table.get("geography_id", "CA-BC"),
                            document_id=response.artifact.document_id,
                            extraction_method="html_table",
                            metadata={
                                "table_id": table["table_id"],
                                "table_title": table.get("title"),
                                "row_label": row[0],
                                "source_year_parameter": table.get("source_year_parameter"),
                            },
                        )
                    )
        return result

    @staticmethod
    def _rows(soup: BeautifulSoup) -> list[list[str]]:
        candidates: list[list[str]] = []
        for table in soup.find_all("table"):
            table_rows: list[list[str]] = []
            for tr in table.find_all("tr"):
                cells = [
                    re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip()
                    for cell in tr.find_all(["th", "td"])
                ]
                if cells:
                    table_rows.append(cells)
            if len(table_rows) > len(candidates):
                candidates = table_rows
        return candidates

    @staticmethod
    def _years(rows: list[list[str]]) -> tuple[list[int], int]:
        for index, row in enumerate(rows):
            years = [int(value) for value in row if re.fullmatch(r"20\d{2}", value)]
            if len(years) >= 2:
                return years, index
        return [], -1

    @staticmethod
    def _number(value: str) -> float | None:
        text = value.replace(",", "").replace("%", "").strip()
        if text in {"", "-", "..", "N/A", "n/a"}:
            return None
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        return float(match.group()) if match else None
