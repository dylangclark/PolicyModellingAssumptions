from __future__ import annotations

from datetime import date

from .base import SourceAdapter
from ..historical_parsers import (
    HistoricalExtractionError,
    discover_fortis_annual_mda,
    parse_fortis_annual_mda,
)
from ..models import CollectionResult, Record
from ..pdf_text import extract_pdf_text, structural_fingerprint


class FortisBCHistoryAdapter(SourceAdapter):
    """Discover and backfill annual FEI/FBC MD&A results from the investor index."""

    def collect(self, full_refresh: bool = False) -> CollectionResult:
        result = CollectionResult(self.source_id)
        index = self.http.request_bytes(
            self.source_id,
            "GET",
            self.source["discovery_url"],
            label="fortisbc_investor_index",
            timeout_seconds=int(self.source.get("timeout_seconds", 240)),
        )
        result.artifacts.append(index.artifact)
        html = index.content.decode("utf-8", errors="replace")
        documents = discover_fortis_annual_mda(
            html,
            self.source["discovery_url"],
            start_year=int(self.source.get("start_year", 2021)),
            end_year=int(self.source.get("end_year", date.today().year - 1)),
        )
        expected_count = int(self.source.get("minimum_document_count", 10))
        if len(documents) < expected_count:
            raise HistoricalExtractionError(
                f"FortisBC discovery found {len(documents)} annual MD&A documents; "
                f"minimum is {expected_count}"
            )
        for document in documents:
            response = self.http.request_bytes(
                self.source_id,
                "GET",
                document.url,
                label=f"fortis_{document.utility}_{document.year}_annual_mda",
                timeout_seconds=int(self.source.get("timeout_seconds", 240)),
            )
            result.artifacts.append(response.artifact)
            text = extract_pdf_text(response.content, require_pdftotext=True, mode="layout")
            values = parse_fortis_annual_mda(text, document.utility, document.year)
            if not values:
                raise HistoricalExtractionError(
                    f"FortisBC {document.utility} {document.year} produced no values"
                )
            publication_date = None
            # Publication dates are in each MD&A title page; capture that where possible.
            import re
            match = re.search(
                r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2}",
                text,
            )
            if match:
                from datetime import datetime
                publication_date = datetime.strptime(match.group(0), "%B %d, %Y").date().isoformat()
            publication_date = publication_date or f"{document.year + 1}-03-31"
            for item in values:
                if item.record_kind == "observation":
                    reference_start = f"{document.year}-01-01"
                    reference_end = f"{document.year}-12-31"
                    target_start = target_end = None
                elif item.target_year is not None:
                    reference_start = reference_end = publication_date
                    target_start = f"{item.target_year}-01-01"
                    target_end = f"{item.target_year}-12-31"
                else:
                    reference_start = reference_end = publication_date
                    target_start = target_end = None
                result.records.append(
                    Record(
                        variable_id=item.variable_id,
                        source_id=self.source_id,
                        source_series_id=item.source_series_id,
                        value=item.value,
                        unit_original=item.unit,
                        unit_canonical=item.unit,
                        reference_period_start=reference_start,
                        reference_period_end=reference_end,
                        target_period_start=target_start,
                        target_period_end=target_end,
                        period_basis=item.period_basis,
                        publication_date=publication_date,
                        vintage_date=publication_date,
                        record_kind=item.record_kind,
                        geography_id="CA-BC",
                        entity_id=item.entity_id,
                        document_id=response.artifact.document_id,
                        evidence_table=item.evidence_table,
                        evidence_text=item.evidence_text,
                        extraction_method="fortisbc_index_pdftotext",
                        metadata={
                            **item.metadata,
                            "evidence_type": item.metadata.get(
                                "evidence_type",
                                "observed"
                                if item.record_kind == "observation"
                                else "utility_forecast",
                            ),
                            "utility": document.utility,
                            "filing_year": document.year,
                            "document_title": document.title,
                            "document_sha256": response.artifact.sha256,
                            "structural_fingerprint": structural_fingerprint(text),
                            "discovery_document_id": index.artifact.document_id,
                            "decision_context": item.metadata.get(
                                "decision_context",
                                "utility financial results"
                                if item.record_kind == "observation"
                                else "FortisBC regulatory and financial planning",
                            ),
                        },
                    )
                )
        return result
