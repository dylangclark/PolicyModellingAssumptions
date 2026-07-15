from __future__ import annotations

from datetime import date

from .base import SourceAdapter
from ..historical_parsers import (
    HistoricalExtractionError,
    parse_bc_budget_2026_raw,
    parse_bc_budget_standard_tables,
)
from ..models import CollectionResult, Record
from ..pdf_text import extract_pdf_text, structural_fingerprint


class BCBudgetHistoryAdapter(SourceAdapter):
    """Backfill B.C. Budget forecast vintages from 2021 onward."""

    def collect(self, full_refresh: bool = False) -> CollectionResult:
        result = CollectionResult(self.source_id)
        documents = self.source.get("documents", [])
        expected_years = {int(value) for value in self.source.get("expected_editions", [])}
        configured_years = {int(document["edition_year"]) for document in documents}
        if expected_years and configured_years != expected_years:
            raise HistoricalExtractionError(
                f"B.C. Budget document manifest mismatch: expected {sorted(expected_years)}, "
                f"configured {sorted(configured_years)}"
            )
        for document in documents:
            response = self.http.request_bytes(
                self.source_id,
                "GET",
                document["url"],
                label=document["document_id"],
                timeout_seconds=int(self.source.get("timeout_seconds", 240)),
            )
            result.artifacts.append(response.artifact)
            year = int(document["edition_year"])
            layout_text: str | None = None
            raw_text: str | None = None
            if year <= 2025:
                layout_text = extract_pdf_text(
                    response.content, require_pdftotext=True, mode="layout"
                )
                values = parse_bc_budget_standard_tables(layout_text, year)
            elif year == 2026:
                raw_text = extract_pdf_text(
                    response.content, require_pdftotext=True, mode="raw"
                )
                values = parse_bc_budget_2026_raw(raw_text)
            else:
                raise HistoricalExtractionError(
                    f"B.C. Budget {year} has not been approved as a parser generation"
                )
            minimum = int(document.get("minimum_records", 8))
            if len(values) < minimum:
                raise HistoricalExtractionError(
                    f"B.C. Budget {year} produced {len(values)} records; minimum is {minimum}"
                )
            for item in values:
                target_start = target_end = None
                if item.target_year is not None:
                    target_start = date(item.target_year, 1, 1).isoformat()
                    target_end = date(item.target_year, 12, 31).isoformat()
                result.records.append(
                    Record(
                        variable_id=item.variable_id,
                        source_id=self.source_id,
                        source_series_id=item.source_series_id,
                        value=item.value,
                        unit_original=item.unit,
                        unit_canonical=item.unit,
                        reference_period_start=document["publication_date"],
                        reference_period_end=document["publication_date"],
                        target_period_start=target_start,
                        target_period_end=target_end,
                        period_basis=item.period_basis,
                        publication_date=document["publication_date"],
                        vintage_date=document["publication_date"],
                        record_kind=item.record_kind,
                        geography_id="CA-BC",
                        scenario_original=item.scenario,
                        scenario_family="reference",
                        document_id=response.artifact.document_id,
                        evidence_table=item.evidence_table,
                        evidence_text=item.evidence_text,
                        extraction_method="pdftotext_historical_tables",
                        metadata={
                            **item.metadata,
                            "evidence_type": item.metadata.get(
                                "evidence_type", "government_forecast"
                            ),
                            "budget_edition": document.get("edition"),
                            "edition_year": year,
                            "document_sha256": response.artifact.sha256,
                            "structural_fingerprint_layout": (
                                structural_fingerprint(layout_text) if layout_text else None
                            ),
                            "structural_fingerprint_raw": (
                                structural_fingerprint(raw_text) if raw_text else None
                            ),
                            "decision_context": "B.C. Budget and Fiscal Plan",
                        },
                    )
                )
        return result
