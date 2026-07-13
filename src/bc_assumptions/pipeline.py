from __future__ import annotations

import os
import traceback
from typing import Iterable

from .adapters import get_adapter
from .config import RegistryConfig
from .db import RegistryDB
from .http import HttpClient
from .models import RunSummary
from .release import coverage_blockers_for_source, source_is_required
from .validation import ValidationError, validate_record


class Pipeline:
    def __init__(self, config: RegistryConfig):
        self.config = config
        self.db = RegistryDB(config.paths.db)
        self.client = HttpClient(config.paths.raw_dir)

    def initialize(self) -> None:
        self.db.initialize()
        self.db.sync_config(self.config.variables, self.config.sources)

    def run(
        self,
        source_ids: Iterable[str] | None = None,
        *,
        full_refresh: bool = False,
        strict: bool = False,
    ) -> list[RunSummary]:
        self.initialize()
        requested = set(source_ids or [])
        if requested:
            unknown = requested - set(self.config.sources)
            if unknown:
                raise KeyError(f"Unknown sources: {', '.join(sorted(unknown))}")
            disabled = {
                source_id
                for source_id in requested
                if not self.config.sources[source_id].get("enabled", False)
            }
            if disabled:
                raise KeyError(f"Disabled sources: {', '.join(sorted(disabled))}")

        selected = [
            source
            for source_id, source in self.config.sources.items()
            if (not requested or source_id in requested) and source.get("enabled", False)
        ]
        summaries: list[RunSummary] = []
        for source in selected:
            summary = self._run_source(source, full_refresh=full_refresh)
            summaries.append(summary)
            blocking_skip = summary.status == "skipped" and source.get(
                "required", not source.get("optional", False)
            )
            if strict and (summary.status in {"failed", "partial"} or blocking_skip):
                break
        return summaries

    def _run_source(self, source: dict, *, full_refresh: bool) -> RunSummary:
        run_id = self.db.start_run(source["id"])
        summary = RunSummary(run_id=run_id, source_id=source["id"], status="running")
        required = source_is_required(source)
        try:
            key_name = source.get("api_key_env")
            if key_name and not os.environ.get(key_name):
                message = f"Missing environment variable {key_name}"
                if required:
                    summary.status = "failed"
                    summary.error = message
                else:
                    summary.status = "skipped"
                    summary.warnings.append(message)
                self.db.finish_run(summary)
                return summary

            adapter_class = get_adapter(source["adapter"])
            adapter = adapter_class(source, self.config.variables, self.db, self.client)
            collection = adapter.collect(full_refresh=full_refresh)
            summary.warnings.extend(collection.warnings)
            if collection.skipped_reason:
                if required:
                    summary.status = "failed"
                    summary.error = collection.skipped_reason
                else:
                    summary.status = "skipped"
                    summary.warnings.append(collection.skipped_reason)
                self.db.finish_run(summary)
                return summary

            for artifact in collection.artifacts:
                self.db.register_document(artifact)

            summary.records_seen = len(collection.records)
            for candidate in collection.records:
                try:
                    record = validate_record(
                        candidate,
                        self.config.variables,
                        self.config.validation,
                    )
                    action = self.db.upsert_record(record).action
                except (ValidationError, ValueError, TypeError) as exc:
                    summary.records_rejected += 1
                    summary.warnings.append(str(exc))
                    continue
                if action == "inserted":
                    summary.records_inserted += 1
                elif action == "revised":
                    summary.records_revised += 1
                else:
                    summary.records_unchanged += 1
                allowed_statuses = set(
                    self.config.validation.get("publication", {}).get(
                        "allowed_statuses", ["validated", "approved"]
                    )
                )
                if record.validation_status not in allowed_statuses:
                    summary.records_rejected += 1
                    summary.warnings.append(
                        f"{record.variable_id} {record.reference_period_start} requires "
                        f"review ({record.validation_status})"
                    )

            coverage_blockers = coverage_blockers_for_source(source, self.db)
            if coverage_blockers:
                summary.status = "failed"
                summary.warnings.extend(coverage_blockers)
                summary.error = (
                    f"Source coverage gate failed with {len(coverage_blockers)} blocker(s)"
                )
            else:
                summary.status = "partial" if summary.records_rejected else "success"
        except Exception as exc:
            summary.status = "failed"
            summary.error = f"{type(exc).__name__}: {exc}"
            if os.environ.get("BC_ASSUMPTIONS_DEBUG") == "1":
                summary.warnings.append(traceback.format_exc())
        self.db.finish_run(summary)
        return summary
