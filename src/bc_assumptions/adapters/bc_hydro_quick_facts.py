from __future__ import annotations

import re
from io import BytesIO

from .base import SourceAdapter
from ..models import CollectionResult, Record


class BCHydroQuickFactsAdapter(SourceAdapter):
    """Extract a narrowly defined set of audited metrics from BC Hydro Quick Facts PDF."""

    def collect(self, full_refresh: bool = False) -> CollectionResult:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("pypdf is required for BC Hydro Quick Facts collection") from exc
        response = self.http.request_bytes(self.source_id, "GET", self.source["download_url"], label="quick-facts")
        reader = PdfReader(BytesIO(response.content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        result = CollectionResult(self.source_id, artifacts=[response.artifact])
        result.records.extend(self.parse_text(text, response.artifact.document_id))
        return result

    def parse_text(self, text: str, document_id: str) -> list[Record]:
        normalized = re.sub(r"[ \t]+", " ", text.replace("\u00a0", " "))
        year_match = re.search(r"(20\d{2})\s*/\s*(20\d{2}).{0,120}?(20\d{2})\s*/\s*(20\d{2})", normalized, re.S)
        if not year_match:
            raise ValueError("Could not identify the two fiscal-year columns in BC Hydro Quick Facts")
        fiscal_years = [int(year_match.group(2)), int(year_match.group(4))]
        pattern = self.source.get("peak_regex", r"Peak one-hour integrated\s+System demand\s*\(megawatts\)\s*([\d,]+)\s+([\d,]+)")
        match = re.search(pattern, normalized, re.I | re.S)
        if not match:
            raise ValueError("Could not locate BC Hydro peak-system-demand row")
        values = [float(match.group(1).replace(",", "")), float(match.group(2).replace(",", ""))]
        if any(v < 5000 or v > 20000 for v in values):
            raise ValueError(f"BC Hydro peak demand values outside guardrails: {values}")
        cfg = self.source["series"][0]
        records = []
        for year, value in zip(fiscal_years, values):
            records.append(Record(
                variable_id=cfg["variable_id"], source_id=self.source_id,
                source_series_id=cfg["source_series_id"], value=value,
                unit_original="MW", unit_canonical="MW",
                reference_period_start=f"{year-1}-04-01", reference_period_end=f"{year}-03-31",
                period_basis="fiscal_year", geography_id="BC Hydro service area",
                document_id=document_id, extraction_method="pdf_text",
                evidence_table="BC Hydro Quick Facts",
                publication_date=self.source.get("publication_date"),
                vintage_date=self.source.get("publication_date"),
                metadata={
                    "fiscal_year_end": year,
                    "evidence_type": "observed",
                    "assumption_owner": "BC Hydro",
                    "source_status": "published_annual_result",
                },
            ))
        return records
