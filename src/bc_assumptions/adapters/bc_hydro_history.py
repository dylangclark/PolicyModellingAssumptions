from __future__ import annotations

from datetime import date

from .base import SourceAdapter
from ..historical_parsers import (
    HistoricalExtractionError,
    parse_bchydro_annual_report,
    parse_bchydro_service_plan,
)
from ..models import CollectionResult, Record
from ..pdf_text import extract_pdf_text, structural_fingerprint


class BCHydroHistoryAdapter(SourceAdapter):
    """Collect BC Hydro plan vintages and corresponding annual actual results."""

    def collect(self, full_refresh: bool = False) -> CollectionResult:
        result = CollectionResult(self.source_id)
        documents = self.source.get("documents", [])
        expected = set(self.source.get("expected_document_ids", []))
        configured = {document["document_id"] for document in documents}
        if expected and expected != configured:
            raise HistoricalExtractionError(
                f"BC Hydro document manifest mismatch; missing={sorted(expected-configured)}, "
                f"unexpected={sorted(configured-expected)}"
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
            text = extract_pdf_text(response.content, require_pdftotext=True, mode="layout")
            if document["document_type"] == "service_plan":
                values = parse_bchydro_service_plan(text, int(document["edition_start_year"]))
            elif document["document_type"] == "annual_service_plan_report":
                values = parse_bchydro_annual_report(text, int(document["fiscal_end_year"]))
            else:
                raise HistoricalExtractionError(
                    f"Unknown BC Hydro document type {document['document_type']!r}"
                )
            minimum = int(document.get("minimum_records", 2))
            if len(values) < minimum:
                raise HistoricalExtractionError(
                    f"{document['document_id']} produced {len(values)} records; minimum {minimum}"
                )
            for item in values:
                if item.period_basis == "fiscal_year_bc" and item.target_year is not None:
                    period_start = date(item.target_year - 1, 4, 1).isoformat()
                    period_end = date(item.target_year, 3, 31).isoformat()
                elif item.target_year is not None:
                    period_start = date(item.target_year, 1, 1).isoformat()
                    period_end = date(item.target_year, 12, 31).isoformat()
                else:
                    period_start = period_end = document["publication_date"]
                if item.record_kind == "observation":
                    reference_start, reference_end = period_start, period_end
                    target_start = target_end = None
                else:
                    reference_start = reference_end = document["publication_date"]
                    target_start, target_end = period_start, period_end
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
                        publication_date=document["publication_date"],
                        vintage_date=document["publication_date"],
                        record_kind=item.record_kind,
                        geography_id="CA-BC-HYDRO",
                        entity_id="bc_hydro",
                        scenario_original=item.scenario,
                        scenario_family="reference" if item.record_kind != "observation" else None,
                        document_id=response.artifact.document_id,
                        evidence_table=item.evidence_table,
                        evidence_text=item.evidence_text,
                        extraction_method="pdftotext_historical_tables",
                        metadata={
                            **item.metadata,
                            "evidence_type": item.metadata.get(
                                "evidence_type",
                                "observed"
                                if item.record_kind == "observation"
                                else "utility_forecast",
                            ),
                            "document_type": document["document_type"],
                            "edition": document.get("edition"),
                            "document_sha256": response.artifact.sha256,
                            "structural_fingerprint": structural_fingerprint(text),
                            "decision_context": (
                                "BC Hydro Service Plan"
                                if item.record_kind != "observation"
                                else "BC Hydro Annual Service Plan Report"
                            ),
                        },
                    )
                )
        return result
