from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Iterable

from .recipe import Candidate
from ..models import utc_now


class ReviewQueue:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[Candidate]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [Candidate(**row) for row in data]

    def save(self, candidates: list[Candidate]) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps([row.as_dict() for row in candidates], indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def add(self, new_candidates: Iterable[Candidate]) -> tuple[int, int]:
        existing = self.load()
        by_id = {row.candidate_id: row for row in existing}
        added = 0
        unchanged = 0
        for candidate in new_candidates:
            if candidate.candidate_id in by_id:
                unchanged += 1
            else:
                by_id[candidate.candidate_id] = candidate
                added += 1
        self.save(
            sorted(by_id.values(), key=lambda row: (row.status, row.created_at, row.candidate_id))
        )
        return added, unchanged

    def list(self, status: str | None = None) -> list[Candidate]:
        rows = self.load()
        return [row for row in rows if status is None or row.status == status]

    def decide(
        self,
        candidate_id: str,
        *,
        decision: str,
        reviewer: str,
        note: str | None = None,
    ) -> Candidate:
        if decision not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected")
        rows = self.load()
        for index, row in enumerate(rows):
            if row.candidate_id == candidate_id:
                updated = replace(
                    row,
                    status=decision,
                    reviewer=reviewer,
                    review_note=note,
                    reviewed_at=utc_now(),
                )
                rows[index] = updated
                self.save(rows)
                return updated
        raise KeyError(f"Candidate not found: {candidate_id}")
