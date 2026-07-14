from __future__ import annotations

from datetime import date
from io import BytesIO
import re
from typing import Any

from pypdf import PdfReader

from .base import SourceAdapter
from ..models import CollectionResult, Record


class BCBudgetForecastAdapter(SourceAdapter):
    """Extract a controlled set of recurring B.C. Budget forecast assumptions.

    Each configured document defines page-local regular expressions and target years.
    A failed match blocks only this optional source and is recorded clearly in the run log.
    """

    def collect(self, full_refresh: bool = False) -> CollectionResult:
        result = CollectionResult(self.source_id)
        for document in self.source.get("documents", []):
            response = self.http.request_bytes(
                self.source_id,
                "GET",
                document["url"],
                label=document["document_id"],
                timeout_seconds=int(self.source.get("timeout_seconds", 180)),
            )
            result.artifacts.append(response.artifact)
            reader = PdfReader(BytesIO(response.content))
            page_cache: dict[int, str] = {}
            for config in document.get("series", []):
                page_numbers = [int(value) for value in config.get("pages", [])]
                text = "\n".join(
                    page_cache.setdefault(page, reader.pages[page - 1].extract_text() or "")
                    for page in page_numbers
                    if 1 <= page <= len(reader.pages)
                )
                normalized = self._normalize(text)
                match = re.search(config["pattern"], normalized, re.IGNORECASE | re.DOTALL)
                if not match:
                    result.warnings.append(
                        f"B.C. Budget {document['document_id']} series "
                        f"{config['source_series_id']} did not match pages {page_numbers}"
                    )
                    continue
                values = [self._number(value) for value in match.groups()]
                years = [int(value) for value in config["target_years"]]
                if len(values) != len(years) or any(value is None for value in values):
                    result.warnings.append(
                        f"B.C. Budget {config['source_series_id']} captured invalid values {values}"
                    )
                    continue
                for year, value in zip(years, values):
                    canonical_value = float(value) * float(config.get("multiplier", 1.0))
                    if config.get("invert"):
                        canonical_value = 1.0 / canonical_value
                    result.records.append(
                        Record(
                            variable_id=config["variable_id"],
                            source_id=self.source_id,
                            source_series_id=config["source_series_id"],
                            value=canonical_value,
                            unit_original=config["unit_original"],
                            unit_canonical=config["unit_canonical"],
                            reference_period_start=document["publication_date"],
                            reference_period_end=document["publication_date"],
                            target_period_start=date(year, 1, 1).isoformat(),
                            target_period_end=date(year, 12, 31).isoformat(),
                            period_basis="annual",
                            publication_date=document["publication_date"],
                            vintage_date=document["publication_date"],
                            record_kind="forecast",
                            geography_id=config.get("geography_id"),
                            scenario_original=config.get("scenario_original", "Budget forecast"),
                            scenario_family="reference",
                            document_id=response.artifact.document_id,
                            evidence_page=", ".join(str(value) for value in page_numbers),
                            evidence_table=config.get("evidence_table"),
                            evidence_text=match.group(0)[:1000],
                            extraction_method="pdf_text_regex",
                            metadata={
                                "budget_edition": document.get("edition"),
                                "document_title": document.get("title"),
                            },
                        )
                    )
        return result

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.replace("/uni00A0", " ").replace("\u00a0", " ")
        text = text.replace("/f_", "")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            return None
