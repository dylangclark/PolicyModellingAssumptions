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
                value_multipliers = config.get("value_multipliers")
                if value_multipliers is not None and len(value_multipliers) != len(values):
                    result.warnings.append(
                        f"B.C. Budget {config['source_series_id']} defines "
                        f"{len(value_multipliers)} value multipliers for {len(values)} values"
                    )
                    continue
                for index, (year, value) in enumerate(zip(years, values)):
                    per_value_multiplier = (
                        float(value_multipliers[index]) if value_multipliers is not None else 1.0
                    )
                    canonical_value = (
                        float(value)
                        * float(config.get("multiplier", 1.0))
                        * per_value_multiplier
                    )
                    if config.get("invert"):
                        if canonical_value == 0:
                            result.warnings.append(
                                f"B.C. Budget {config['source_series_id']} cannot invert zero"
                            )
                            continue
                        canonical_value = 1.0 / canonical_value
                    hard_min = config.get("hard_min")
                    hard_max = config.get("hard_max")
                    if (hard_min is not None and canonical_value < float(hard_min)) or (
                        hard_max is not None and canonical_value > float(hard_max)
                    ):
                        result.warnings.append(
                            f"B.C. Budget {config['source_series_id']} value "
                            f"{canonical_value} is outside hard bounds"
                        )
                        continue
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
                                "evidence_type": config.get(
                                    "evidence_type", "government_forecast"
                                ),
                                "assumption_owner": config.get(
                                    "assumption_owner", "B.C. Ministry of Finance"
                                ),
                                "source_status": config.get(
                                    "source_status", "published_budget_forecast"
                                ),
                                "decision_context": config.get(
                                    "decision_context", "B.C. Budget and Fiscal Plan"
                                ),
                            },
                        )
                    )
        return result

    @staticmethod
    def _normalize(text: str) -> str:
        substitutions = {
            "/uni00A0": " ",
            "\u00a0": " ",
            "/f_": "",
            "/T_": "T",
            "\ufb01": "fi",
            "\ufb02": "fl",
            "\u2212": "-",
            "\u2013": "-",
            "\u2014": "-",
        }
        for old, new in substitutions.items():
            text = text.replace(old, new)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            return None
