from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator
from uuid import uuid4

from .models import Artifact, Record, RunSummary, UpsertResult, utc_now


SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS variables (
    variable_id TEXT PRIMARY KEY,
    class_name TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    canonical_unit TEXT NOT NULL,
    geography_id TEXT,
    config_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    publisher TEXT NOT NULL,
    authority_tier INTEGER,
    adapter TEXT NOT NULL,
    source_url TEXT,
    enabled INTEGER NOT NULL,
    config_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    local_path TEXT NOT NULL,
    content_type TEXT,
    retrieved_at TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    request_method TEXT NOT NULL,
    request_metadata_json TEXT NOT NULL,
    response_headers_json TEXT NOT NULL,
    FOREIGN KEY(source_id) REFERENCES sources(source_id)
);

CREATE INDEX IF NOT EXISTS ix_documents_source_sha
ON documents(source_id, sha256);

CREATE TABLE IF NOT EXISTS records (
    record_id TEXT PRIMARY KEY,
    natural_key_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    variable_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_series_id TEXT NOT NULL,
    value REAL,
    range_low REAL,
    range_high REAL,
    unit_original TEXT NOT NULL,
    unit_canonical TEXT NOT NULL,
    record_kind TEXT NOT NULL,
    geography_id TEXT,
    entity_id TEXT,
    reference_period_start TEXT NOT NULL,
    reference_period_end TEXT NOT NULL,
    target_period_start TEXT,
    target_period_end TEXT,
    period_basis TEXT,
    publication_date TEXT,
    vintage_date TEXT,
    scenario_original TEXT,
    scenario_family TEXT,
    statistic_type TEXT,
    currency TEXT,
    price_base_year INTEGER,
    real_or_nominal TEXT,
    document_id TEXT,
    evidence_page TEXT,
    evidence_table TEXT,
    evidence_text TEXT,
    extraction_method TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    quality_flags_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    is_current INTEGER NOT NULL DEFAULT 1,
    supersedes_record_id TEXT,
    FOREIGN KEY(variable_id) REFERENCES variables(variable_id),
    FOREIGN KEY(source_id) REFERENCES sources(source_id),
    FOREIGN KEY(document_id) REFERENCES documents(document_id),
    FOREIGN KEY(supersedes_record_id) REFERENCES records(record_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_records_current_natural_key
ON records(natural_key_hash) WHERE is_current = 1;

CREATE INDEX IF NOT EXISTS ix_records_variable_period
ON records(variable_id, reference_period_start);

CREATE INDEX IF NOT EXISTS ix_records_source_series
ON records(source_id, source_series_id, reference_period_start);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    records_seen INTEGER NOT NULL DEFAULT 0,
    records_inserted INTEGER NOT NULL DEFAULT 0,
    records_revised INTEGER NOT NULL DEFAULT 0,
    records_unchanged INTEGER NOT NULL DEFAULT 0,
    records_rejected INTEGER NOT NULL DEFAULT 0,
    warnings_json TEXT NOT NULL DEFAULT '[]',
    error TEXT,
    FOREIGN KEY(source_id) REFERENCES sources(source_id)
);

CREATE TABLE IF NOT EXISTS extraction_candidates (
    candidate_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    variable_id TEXT,
    proposed_record_json TEXT NOT NULL,
    evidence_page TEXT,
    evidence_text TEXT,
    extraction_rule_id TEXT,
    confidence REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewer_note TEXT,
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    approved_record_id TEXT,
    FOREIGN KEY(document_id) REFERENCES documents(document_id),
    FOREIGN KEY(source_id) REFERENCES sources(source_id),
    FOREIGN KEY(variable_id) REFERENCES variables(variable_id),
    FOREIGN KEY(approved_record_id) REFERENCES records(record_id)
);
"""


class RegistryDB:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def sync_config(
        self,
        variables: dict[str, dict[str, Any]],
        sources: dict[str, dict[str, Any]],
    ) -> None:
        now = utc_now()
        with self.connect() as connection:
            for variable_id, row in variables.items():
                connection.execute(
                    """
                    INSERT INTO variables (
                        variable_id, class_name, name, description, canonical_unit,
                        geography_id, config_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(variable_id) DO UPDATE SET
                        class_name=excluded.class_name,
                        name=excluded.name,
                        description=excluded.description,
                        canonical_unit=excluded.canonical_unit,
                        geography_id=excluded.geography_id,
                        config_json=excluded.config_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        variable_id,
                        row["class"],
                        row["name"],
                        row.get("description"),
                        row["canonical_unit"],
                        row.get("geography_id"),
                        json.dumps(row, sort_keys=True),
                        now,
                    ),
                )
            for source_id, row in sources.items():
                connection.execute(
                    """
                    INSERT INTO sources (
                        source_id, name, publisher, authority_tier, adapter,
                        source_url, enabled, config_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id) DO UPDATE SET
                        name=excluded.name,
                        publisher=excluded.publisher,
                        authority_tier=excluded.authority_tier,
                        adapter=excluded.adapter,
                        source_url=excluded.source_url,
                        enabled=excluded.enabled,
                        config_json=excluded.config_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        source_id,
                        row["name"],
                        row["publisher"],
                        row.get("authority_tier"),
                        row["adapter"],
                        row.get("source_url"),
                        1 if row.get("enabled", False) else 0,
                        json.dumps(row, sort_keys=True),
                        now,
                    ),
                )

    def register_document(self, artifact: Artifact) -> str:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    document_id, source_id, source_url, local_path, content_type,
                    retrieved_at, sha256, size_bytes, request_method,
                    request_metadata_json, response_headers_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    local_path=excluded.local_path,
                    retrieved_at=excluded.retrieved_at,
                    source_url=excluded.source_url,
                    content_type=excluded.content_type,
                    size_bytes=excluded.size_bytes,
                    request_metadata_json=excluded.request_metadata_json,
                    response_headers_json=excluded.response_headers_json
                """,
                (
                    artifact.document_id,
                    artifact.source_id,
                    artifact.source_url,
                    artifact.local_path,
                    artifact.content_type,
                    artifact.retrieved_at,
                    artifact.sha256,
                    artifact.size_bytes,
                    artifact.request_method,
                    json.dumps(artifact.request_metadata, sort_keys=True),
                    json.dumps(artifact.response_headers, sort_keys=True),
                ),
            )
        return artifact.document_id

    def upsert_record(self, record: Record) -> UpsertResult:
        now = utc_now()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM records WHERE natural_key_hash=? AND is_current=1",
                (record.natural_key_hash,),
            ).fetchone()
            if existing and existing["payload_hash"] == record.payload_hash:
                connection.execute(
                    """
                    UPDATE records SET
                        last_seen_at=?,
                        document_id=COALESCE(?, document_id),
                        publication_date=COALESCE(?, publication_date),
                        vintage_date=COALESCE(?, vintage_date),
                        evidence_page=COALESCE(?, evidence_page),
                        evidence_table=COALESCE(?, evidence_table),
                        evidence_text=COALESCE(?, evidence_text),
                        metadata_json=?
                    WHERE record_id=?
                    """,
                    (
                        now,
                        record.document_id,
                        record.publication_date,
                        record.vintage_date,
                        record.evidence_page,
                        record.evidence_table,
                        record.evidence_text,
                        json.dumps(record.metadata, sort_keys=True),
                        existing["record_id"],
                    ),
                )
                return UpsertResult("unchanged", existing["record_id"])

            supersedes = existing["record_id"] if existing else None
            if existing:
                connection.execute(
                    "UPDATE records SET is_current=0, valid_to=?, last_seen_at=? WHERE record_id=?",
                    (now, now, existing["record_id"]),
                )

            connection.execute(
                """
                INSERT INTO records (
                    record_id, natural_key_hash, payload_hash, variable_id, source_id,
                    source_series_id, value, range_low, range_high, unit_original,
                    unit_canonical, record_kind, geography_id, entity_id,
                    reference_period_start, reference_period_end, target_period_start,
                    target_period_end, period_basis, publication_date, vintage_date,
                    scenario_original, scenario_family, statistic_type, currency,
                    price_base_year, real_or_nominal, document_id, evidence_page,
                    evidence_table, evidence_text, extraction_method, validation_status,
                    quality_flags_json, metadata_json, first_seen_at, last_seen_at,
                    valid_from, valid_to, is_current, supersedes_record_id
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 1, ?
                )
                """,
                (
                    record.record_id,
                    record.natural_key_hash,
                    record.payload_hash,
                    record.variable_id,
                    record.source_id,
                    record.source_series_id,
                    record.value,
                    record.range_low,
                    record.range_high,
                    record.unit_original,
                    record.unit_canonical,
                    record.record_kind,
                    record.geography_id,
                    record.entity_id,
                    record.reference_period_start,
                    record.reference_period_end,
                    record.target_period_start,
                    record.target_period_end,
                    record.period_basis,
                    record.publication_date,
                    record.vintage_date,
                    record.scenario_original,
                    record.scenario_family,
                    record.statistic_type,
                    record.currency,
                    record.price_base_year,
                    record.real_or_nominal,
                    record.document_id,
                    record.evidence_page,
                    record.evidence_table,
                    record.evidence_text,
                    record.extraction_method,
                    record.validation_status,
                    json.dumps(record.quality_flags, sort_keys=True),
                    json.dumps(record.metadata, sort_keys=True),
                    now,
                    now,
                    now,
                    supersedes,
                ),
            )
            return UpsertResult("revised" if existing else "inserted", record.record_id)

    def latest_reference_start(self, source_id: str, source_series_id: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT MAX(reference_period_start) AS latest
                FROM records
                WHERE source_id=? AND source_series_id=? AND is_current=1
                """,
                (source_id, source_series_id),
            ).fetchone()
            return row["latest"] if row and row["latest"] else None

    def latest_run(self, source_id: str) -> dict[str, Any] | None:
        rows = self.query(
            """
            SELECT * FROM runs
            WHERE source_id=?
            ORDER BY started_at DESC, run_id DESC
            LIMIT 1
            """,
            (source_id,),
        )
        return rows[0] if rows else None

    def coverage_rows(self, source_id: str) -> list[dict[str, Any]]:
        return self.query(
            """
            SELECT source_series_id, variable_id,
                   MAX(reference_period_end) AS latest_period,
                   COUNT(*) AS current_record_count
            FROM records
            WHERE source_id=? AND is_current=1
            GROUP BY source_series_id, variable_id
            ORDER BY source_series_id, variable_id
            """,
            (source_id,),
        )

    def start_run(self, source_id: str) -> str:
        run_id = f"run_{uuid4().hex}"
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO runs(run_id, source_id, started_at, status) VALUES (?, ?, ?, 'running')",
                (run_id, source_id, utc_now()),
            )
        return run_id

    def finish_run(self, summary: RunSummary) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE runs SET
                    finished_at=?, status=?, records_seen=?, records_inserted=?,
                    records_revised=?, records_unchanged=?, records_rejected=?,
                    warnings_json=?, error=?
                WHERE run_id=?
                """,
                (
                    utc_now(),
                    summary.status,
                    summary.records_seen,
                    summary.records_inserted,
                    summary.records_revised,
                    summary.records_unchanged,
                    summary.records_rejected,
                    json.dumps(summary.warnings, sort_keys=True),
                    summary.error,
                    summary.run_id,
                ),
            )

    def query(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
            return [dict(row) for row in rows]

    def current_records(self, publishable_only: bool = False) -> list[dict[str, Any]]:
        where = "WHERE r.is_current=1"
        if publishable_only:
            where += " AND r.validation_status IN ('validated', 'approved')"
        return self.query(
            f"""
            SELECT r.*, v.class_name, v.name AS variable_name,
                   s.name AS source_name, s.publisher, s.source_url,
                   d.source_url AS document_url, d.sha256 AS document_sha256,
                   d.retrieved_at AS document_retrieved_at
            FROM records r
            JOIN variables v ON r.variable_id=v.variable_id
            JOIN sources s ON r.source_id=s.source_id
            LEFT JOIN documents d ON r.document_id=d.document_id
            {where}
            ORDER BY r.variable_id, r.reference_period_start, r.source_id
            """
        )

    def history_records(self) -> list[dict[str, Any]]:
        return self.query(
            """
            SELECT r.*, v.class_name, v.name AS variable_name,
                   s.name AS source_name, s.publisher, s.source_url,
                   d.source_url AS document_url, d.sha256 AS document_sha256,
                   d.retrieved_at AS document_retrieved_at
            FROM records r
            JOIN variables v ON r.variable_id=v.variable_id
            JOIN sources s ON r.source_id=s.source_id
            LEFT JOIN documents d ON r.document_id=d.document_id
            ORDER BY r.variable_id, r.reference_period_start, r.valid_from
            """
        )

    def table_rows(self, table: str) -> list[dict[str, Any]]:
        if table not in {
            "variables",
            "sources",
            "documents",
            "runs",
            "extraction_candidates",
        }:
            raise ValueError(f"Unsupported table: {table}")
        return self.query(f"SELECT * FROM {table} ORDER BY 1")
