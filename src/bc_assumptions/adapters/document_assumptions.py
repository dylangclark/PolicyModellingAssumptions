from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from io import BytesIO
import re
from typing import Any

from pypdf import PdfReader

from .base import SourceAdapter
from ..models import CollectionResult, Record


class DocumentExtractionError(ValueError):
    """Raised when a controlled document recipe no longer matches its source."""


@dataclass(frozen=True, slots=True)
class ExtractedValue:
    value: float
    reference_period_start: str
    reference_period_end: str
    target_period_start: str | None
    target_period_end: str | None
    label: str | None = None


def normalize_pdf_text(text: str) -> str:
    substitutions = {
        "\u00a0": " ",
        "\u2212": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "/uni00A0": " ",
        "/f_": "",
    }
    for old, new in substitutions.items():
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()


def parse_number(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        return float(value)
    token = str(value).strip()
    if not token or token in {"-", "--", "n/a", "N/A"}:
        return None
    negative = token.startswith("(") and token.endswith(")")
    token = token.strip("()").replace(",", "").replace("$", "").replace("%", "")
    token = token.replace(" ", "")
    try:
        result = float(token)
    except ValueError:
        return None
    return -result if negative else result


def _period_for_year(year: int, basis: str) -> tuple[str, str]:
    if basis == "fiscal_year_bc":
        return f"{year - 1}-04-01", f"{year}-03-31"
    return f"{year}-01-01", f"{year}-12-31"


def _period_for_quarter(year: int, quarter: int) -> tuple[str, str]:
    if quarter not in {1, 2, 3, 4}:
        raise DocumentExtractionError(f"Invalid quarter: {quarter}")
    starts = {1: (1, 1), 2: (4, 1), 3: (7, 1), 4: (10, 1)}
    ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    sm, sd = starts[quarter]
    em, ed = ends[quarter]
    return date(year, sm, sd).isoformat(), date(year, em, ed).isoformat()


def _format_date(value: str, context: dict[str, Any]) -> str:
    try:
        return value.format(**context)
    except (KeyError, ValueError) as exc:
        raise DocumentExtractionError(f"Could not format date {value!r}: {exc}") from exc


def _apply_transform(value: float, config: dict[str, Any]) -> float:
    result = value * float(config.get("multiplier", 1.0))
    divisor = float(config.get("divisor", 1.0))
    if divisor == 0:
        raise DocumentExtractionError("Document recipe divisor cannot be zero")
    result /= divisor
    if config.get("invert"):
        if result == 0:
            raise DocumentExtractionError("Cannot invert zero in document recipe")
        result = 1.0 / result
    return result


def _hard_guard(value: float, config: dict[str, Any], series_id: str) -> None:
    minimum = config.get("hard_min")
    maximum = config.get("hard_max")
    if minimum is not None and value < float(minimum):
        raise DocumentExtractionError(
            f"{series_id} value {value} is below hard minimum {minimum}"
        )
    if maximum is not None and value > float(maximum):
        raise DocumentExtractionError(
            f"{series_id} value {value} is above hard maximum {maximum}"
        )


def _value_specs(series: dict[str, Any], match: re.Match[str]) -> list[dict[str, Any]]:
    specs = series.get("values")
    if specs:
        return [dict(spec) for spec in specs]

    years = series.get("target_years")
    if years:
        groups = list(match.groups())
        if len(groups) != len(years):
            raise DocumentExtractionError(
                f"{series['source_series_id']} captured {len(groups)} values for "
                f"{len(years)} target years"
            )
        return [
            {"group_index": index + 1, "target_year": int(year)}
            for index, year in enumerate(years)
        ]

    return [{"group": series.get("value_group", "value")}]


def _raw_group(match: re.Match[str], spec: dict[str, Any]) -> str | None:
    if "group" in spec:
        try:
            return match.group(str(spec["group"]))
        except (IndexError, KeyError) as exc:
            raise DocumentExtractionError(
                f"Missing named capture group {spec['group']!r}"
            ) from exc
    if "group_index" in spec:
        try:
            return match.group(int(spec["group_index"]))
        except IndexError as exc:
            raise DocumentExtractionError(
                f"Missing capture group {spec['group_index']}"
            ) from exc
    if match.lastindex == 1:
        return match.group(1)
    try:
        return match.group("value")
    except (IndexError, KeyError):
        return None


def _periods(
    series: dict[str, Any],
    spec: dict[str, Any],
    document: dict[str, Any],
    match: re.Match[str],
) -> tuple[str, str, str | None, str | None, dict[str, Any]]:
    context: dict[str, Any] = {}
    context.update({key: value for key, value in match.groupdict().items() if value is not None})
    context.update({key: value for key, value in document.items() if isinstance(value, (str, int))})
    context.update(spec)

    record_kind = spec.get("record_kind", series.get("record_kind", "forecast"))
    period_basis = spec.get("period_basis", series.get("period_basis", "annual"))

    target_year = spec.get("target_year")
    if target_year is None and spec.get("target_year_group"):
        target_year = int(match.group(spec["target_year_group"]))
    target_quarter = spec.get("target_quarter")
    if target_quarter is None and spec.get("target_quarter_group"):
        target_quarter = int(match.group(spec["target_quarter_group"]))

    if target_year is not None:
        if target_quarter is not None:
            target_start, target_end = _period_for_quarter(int(target_year), int(target_quarter))
        else:
            target_start, target_end = _period_for_year(int(target_year), period_basis)
    else:
        target_start = spec.get("target_period_start", series.get("target_period_start"))
        target_end = spec.get("target_period_end", series.get("target_period_end"))
        if target_start:
            target_start = _format_date(str(target_start), context)
        if target_end:
            target_end = _format_date(str(target_end), context)

    reference_year = spec.get("reference_year")
    if reference_year is None and spec.get("reference_year_group"):
        reference_year = int(match.group(spec["reference_year_group"]))
    reference_quarter = spec.get("reference_quarter")
    if reference_quarter is None and spec.get("reference_quarter_group"):
        reference_quarter = int(match.group(spec["reference_quarter_group"]))

    if record_kind == "model_parameter" or series.get("non_temporal"):
        publication = document.get("publication_date") or document.get("vintage_date")
        if not publication:
            raise DocumentExtractionError(
                f"Non-temporal parameter {series['source_series_id']} requires publication_date"
            )
        reference_start = reference_end = str(publication)[:10]
        target_start = target_end = None
        period_basis = "non_temporal"
    elif reference_year is not None:
        if reference_quarter is not None:
            reference_start, reference_end = _period_for_quarter(
                int(reference_year), int(reference_quarter)
            )
        else:
            reference_start, reference_end = _period_for_year(
                int(reference_year), period_basis
            )
    elif spec.get("reference_period_start") or series.get("reference_period_start"):
        start_template = spec.get(
            "reference_period_start", series.get("reference_period_start")
        )
        end_template = spec.get("reference_period_end", series.get("reference_period_end"))
        if not start_template or not end_template:
            raise DocumentExtractionError(
                f"{series['source_series_id']} must define both reference dates"
            )
        reference_start = _format_date(str(start_template), context)
        reference_end = _format_date(str(end_template), context)
    elif target_start and target_end:
        reference_start, reference_end = target_start, target_end
    else:
        publication = document.get("publication_date") or document.get("vintage_date")
        if not publication:
            raise DocumentExtractionError(
                f"{series['source_series_id']} has no reference period or publication date"
            )
        reference_start = reference_end = str(publication)[:10]

    if record_kind == "observation":
        target_start = target_end = None

    return (
        reference_start,
        reference_end,
        target_start,
        target_end,
        {"period_basis": period_basis, "record_kind": record_kind},
    )


def extract_series_values(
    series: dict[str, Any],
    text: str,
    document: dict[str, Any],
) -> tuple[list[ExtractedValue], re.Match[str]]:
    flags = re.IGNORECASE | re.DOTALL
    pattern = re.compile(series["pattern"], flags)
    matches = list(pattern.finditer(text))
    expected = series.get("expected_matches", 1)
    match_policy = series.get("match_policy", "exact")
    if match_policy == "exact" and len(matches) != int(expected):
        raise DocumentExtractionError(
            f"{series['source_series_id']} expected {expected} match(es), found {len(matches)}"
        )
    if match_policy == "at_least_one" and not matches:
        raise DocumentExtractionError(f"{series['source_series_id']} found no matches")
    if not matches:
        raise DocumentExtractionError(f"{series['source_series_id']} found no matches")

    match_index = int(series.get("match_index", 1)) - 1
    try:
        match = matches[match_index]
    except IndexError as exc:
        raise DocumentExtractionError(
            f"{series['source_series_id']} match_index is outside available matches"
        ) from exc

    output: list[ExtractedValue] = []
    for spec in _value_specs(series, match):
        raw = _raw_group(match, spec)
        value = parse_number(raw)
        if value is None:
            raise DocumentExtractionError(
                f"{series['source_series_id']} captured non-numeric value {raw!r}"
            )
        combined = {**series, **spec}
        value = _apply_transform(value, combined)
        _hard_guard(value, combined, series["source_series_id"])
        ref_start, ref_end, target_start, target_end, _ = _periods(
            series, spec, document, match
        )
        output.append(
            ExtractedValue(
                value=value,
                reference_period_start=ref_start,
                reference_period_end=ref_end,
                target_period_start=target_start,
                target_period_end=target_end,
                label=spec.get("label"),
            )
        )
    return output, match


class DocumentAssumptionsAdapter(SourceAdapter):
    """Extract reviewed observations, forecasts, and parameters from recurring PDFs.

    The adapter is intentionally recipe-driven and fail-closed. A required series must
    match the configured number of times, pass document guards, and remain inside hard
    plausibility limits. Non-temporal parameters are represented as model parameters
    tied to a publication/effective context rather than as a conventional time series.
    """

    def collect(self, full_refresh: bool = False) -> CollectionResult:
        result = CollectionResult(self.source_id)
        for document in self.source.get("documents", []):
            response = self.http.request_bytes(
                self.source_id,
                "GET",
                document["url"],
                label=document["document_id"],
                timeout_seconds=int(self.source.get("timeout_seconds", 240)),
            )
            result.artifacts.append(response.artifact)
            pages = self._pdf_pages(response.content)
            self._guard_document(document, pages)
            for series in document.get("series", []):
                try:
                    records = self._extract_records(
                        document,
                        series,
                        pages,
                        response.artifact.document_id,
                    )
                except DocumentExtractionError as exc:
                    if series.get("required", True):
                        raise
                    result.warnings.append(str(exc))
                    continue
                result.records.extend(records)
        return result

    @staticmethod
    def _pdf_pages(content: bytes) -> list[str]:
        reader = PdfReader(BytesIO(content))
        return [normalize_pdf_text(page.extract_text() or "") for page in reader.pages]

    @staticmethod
    def _guard_document(document: dict[str, Any], pages: list[str]) -> None:
        first_pages = " ".join(pages[: int(document.get("guard_page_count", 5))])
        for pattern in document.get("guard_patterns", []):
            if not re.search(pattern, first_pages, re.IGNORECASE | re.DOTALL):
                raise DocumentExtractionError(
                    f"Document {document['document_id']} failed guard pattern {pattern!r}"
                )

    def _extract_records(
        self,
        document: dict[str, Any],
        series: dict[str, Any],
        pages: list[str],
        document_id: str,
    ) -> list[Record]:
        selected_pages = [int(page) for page in series.get("pages", range(1, len(pages) + 1))]
        invalid = [page for page in selected_pages if page < 1 or page > len(pages)]
        if invalid:
            raise DocumentExtractionError(
                f"{series['source_series_id']} references invalid pages {invalid}"
            )
        text = " ".join(pages[page - 1] for page in selected_pages)
        values, match = extract_series_values(series, text, document)
        records: list[Record] = []
        for index, extracted in enumerate(values, start=1):
            spec = (_value_specs(series, match))[index - 1]
            fields = {**series, **spec}
            _, _, _, _, period_fields = _periods(series, spec, document, match)
            record_kind = period_fields["record_kind"]
            metadata = {
                "document_title": document.get("title"),
                "document_edition": document.get("edition"),
                "decision_context": fields.get("decision_context"),
                "approval_status": fields.get("approval_status"),
                "parameter_scope": fields.get("parameter_scope"),
                "effective_from": fields.get("effective_from"),
                "effective_to": fields.get("effective_to"),
                "evidence_type": fields.get(
                    "evidence_type",
                    document.get("evidence_type", self.source.get("evidence_type")),
                ),
                "assumption_owner": fields.get(
                    "assumption_owner",
                    document.get("assumption_owner", self.source.get("assumption_owner")),
                ),
                "source_status": fields.get(
                    "source_status",
                    document.get("source_status", self.source.get("source_status")),
                ),
                "time_basis": (
                    "non_temporal_parameter"
                    if record_kind == "model_parameter" or series.get("non_temporal")
                    else fields.get("time_basis")
                ),
                "value_label": extracted.label,
                **document.get("metadata", {}),
                **series.get("metadata", {}),
                **spec.get("metadata", {}),
            }
            metadata = {key: value for key, value in metadata.items() if value is not None}
            evidence = match.group(0)
            records.append(
                Record(
                    variable_id=fields["variable_id"],
                    source_id=self.source_id,
                    source_series_id=(
                        fields["source_series_id"]
                        if len(values) == 1
                        else f"{fields['source_series_id']}:{extracted.label or index}"
                    ),
                    value=extracted.value,
                    unit_original=fields["unit_original"],
                    unit_canonical=fields["unit_canonical"],
                    reference_period_start=extracted.reference_period_start,
                    reference_period_end=extracted.reference_period_end,
                    target_period_start=extracted.target_period_start,
                    target_period_end=extracted.target_period_end,
                    period_basis=period_fields["period_basis"],
                    publication_date=document.get("publication_date"),
                    vintage_date=document.get("vintage_date", document.get("publication_date")),
                    record_kind=record_kind,
                    geography_id=fields.get("geography_id", self.source.get("geography_id")),
                    entity_id=fields.get("entity_id", self.source.get("entity_id")),
                    scenario_original=fields.get("scenario_original"),
                    scenario_family=fields.get("scenario_family"),
                    statistic_type=fields.get("statistic_type", "point_estimate"),
                    currency=fields.get("currency"),
                    price_base_year=fields.get("price_base_year"),
                    real_or_nominal=fields.get("real_or_nominal"),
                    document_id=document_id,
                    evidence_page=", ".join(str(page) for page in selected_pages),
                    evidence_table=fields.get("evidence_table"),
                    evidence_text=evidence[:1500],
                    extraction_method="pdf_text_regex_recipe",
                    validation_status=fields.get("validation_status", "validated"),
                    quality_flags=list(fields.get("quality_flags", [])),
                    metadata=metadata,
                )
            )
        return records
