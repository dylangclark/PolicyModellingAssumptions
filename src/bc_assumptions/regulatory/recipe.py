from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
import re
from typing import Any

import yaml

from ..models import stable_hash, utc_now


@dataclass(slots=True)
class Candidate:
    candidate_id: str
    recipe_id: str
    extractor_id: str
    source_id: str
    document_path: str
    document_sha256: str
    variable_id: str
    value: float | None
    range_low: float | None
    range_high: float | None
    unit_original: str
    unit_canonical: str
    record_kind: str
    geography_id: str | None
    reference_period_start: str
    reference_period_end: str
    target_period_start: str | None
    target_period_end: str | None
    scenario_original: str | None
    page: int
    evidence_text: str
    entity_id: str | None = None
    publication_date: str | None = None
    vintage_date: str | None = None
    period_basis: str | None = None
    evidence_type: str | None = None
    assumption_owner: str | None = None
    source_status: str | None = None
    decision_context: str | None = None
    approval_status: str | None = None
    parameter_scope: str | None = None
    time_basis: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    extraction_method: str = "pdf_regex_recipe"
    confidence: float = 1.0
    status: str = "pending"
    reviewer: str | None = None
    review_note: str | None = None
    created_at: str = field(default_factory=utc_now)
    reviewed_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_recipe(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "recipe_id" not in data or "extractors" not in data:
        raise ValueError(f"Invalid regulatory recipe: {path}")
    return data


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.replace(",", "").replace("$", "").replace("%", "").strip()
    if not cleaned:
        return None
    return float(cleaned)


def _evidence(text: str, start: int, end: int, context: int = 180) -> str:
    left = max(0, start - context)
    right = min(len(text), end + context)
    return re.sub(r"\s+", " ", text[left:right]).strip()


def extract_candidates_from_pages(
    recipe: dict[str, Any],
    pages: list[str],
    *,
    document_path: str,
    document_sha256: str,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    defaults = recipe.get("defaults", {})
    for extractor in recipe["extractors"]:
        first_page, last_page = extractor.get("page_range", [1, len(pages)])
        pattern = re.compile(extractor["pattern"], flags=re.IGNORECASE | re.MULTILINE)
        for page_number in range(max(1, int(first_page)), min(len(pages), int(last_page)) + 1):
            text = pages[page_number - 1]
            for match_index, match in enumerate(pattern.finditer(text), start=1):
                groups = match.groupdict()
                value = _number(groups.get(extractor.get("value_group", "value")))
                low = _number(groups.get(extractor.get("range_low_group", "range_low")))
                high = _number(groups.get(extractor.get("range_high_group", "range_high")))
                if value is None and low is None and high is None:
                    continue
                fields = {**defaults, **extractor.get("fields", {})}
                identity = {
                    "recipe": recipe["recipe_id"],
                    "extractor": extractor["id"],
                    "document_sha256": document_sha256,
                    "page": page_number,
                    "match": match.group(0),
                    "match_index": match_index,
                }
                candidates.append(
                    Candidate(
                        candidate_id=f"cand_{stable_hash(identity)[:24]}",
                        recipe_id=recipe["recipe_id"],
                        extractor_id=extractor["id"],
                        source_id=recipe["source_id"],
                        document_path=document_path,
                        document_sha256=document_sha256,
                        variable_id=extractor["variable_id"],
                        value=value,
                        range_low=low,
                        range_high=high,
                        unit_original=extractor["unit_original"],
                        unit_canonical=extractor["unit_canonical"],
                        record_kind=fields.get("record_kind", "model_parameter"),
                        geography_id=fields.get("geography_id"),
                        reference_period_start=fields["reference_period_start"],
                        reference_period_end=fields["reference_period_end"],
                        target_period_start=fields.get("target_period_start"),
                        target_period_end=fields.get("target_period_end"),
                        scenario_original=fields.get("scenario_original"),
                        page=page_number,
                        evidence_text=_evidence(text, match.start(), match.end()),
                        entity_id=fields.get("entity_id"),
                        publication_date=fields.get("publication_date"),
                        vintage_date=fields.get(
                            "vintage_date", fields.get("publication_date")
                        ),
                        period_basis=fields.get("period_basis"),
                        evidence_type=fields.get("evidence_type"),
                        assumption_owner=fields.get("assumption_owner"),
                        source_status=fields.get("source_status"),
                        decision_context=fields.get("decision_context"),
                        approval_status=fields.get("approval_status"),
                        parameter_scope=fields.get("parameter_scope"),
                        time_basis=(
                            "non_temporal_parameter"
                            if fields.get("record_kind") == "model_parameter"
                            else fields.get("time_basis")
                        ),
                        metadata=dict(fields.get("metadata", {})),
                        confidence=float(extractor.get("confidence", 1.0)),
                    )
                )
    return candidates


def extract_pdf_pages(path: Path) -> tuple[list[str], str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "PDF extraction requires the optional dependency: pip install -e '.[regulatory]'"
        ) from exc
    content = path.read_bytes()
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return pages, sha256(content).hexdigest()
