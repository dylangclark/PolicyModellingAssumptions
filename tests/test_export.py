from pathlib import Path

from bc_assumptions.config import RegistryConfig, RepositoryPaths
from bc_assumptions.db import RegistryDB
from bc_assumptions.export import export_registry
from bc_assumptions.models import Record
from bc_assumptions.publication import PublicationError, validate_publication


def test_export_writes_public_json_and_excludes_review_rows(tmp_path: Path):
    paths = RepositoryPaths(
        root=tmp_path,
        db=tmp_path / "state/registry.sqlite",
        raw_dir=tmp_path / "data/raw",
        export_dir=tmp_path / "data/export",
        site_data_dir=tmp_path / "site/data",
        cache_dir=tmp_path / "data/cache",
        review_queue=tmp_path / "state/review_queue.json",
    )
    paths.ensure()
    variables = {
        "x": {
            "id": "x",
            "class": "Economic",
            "name": "Test",
            "description": "Test",
            "canonical_unit": "percent",
            "geography_id": "CA-BC",
        }
    }
    sources = {
        "s": {
            "id": "s",
            "name": "Source",
            "publisher": "Publisher",
            "adapter": "test",
            "enabled": True,
            "publish_enabled": True,
            "source_url": "https://example.test",
        }
    }
    config = RegistryConfig(paths, variables, sources, {}, {})
    db = RegistryDB(paths.db)
    db.initialize()
    db.sync_config(variables, sources)
    good = Record(
        variable_id="x",
        source_id="s",
        source_series_id="a",
        value=1,
        unit_original="percent",
        unit_canonical="percent",
        reference_period_start="2025-01-01",
        reference_period_end="2025-12-31",
    )
    review = Record(
        variable_id="x",
        source_id="s",
        source_series_id="b",
        value=2,
        unit_original="percent",
        unit_canonical="percent",
        reference_period_start="2026-01-01",
        reference_period_end="2026-12-31",
        validation_status="needs_review",
    )
    db.upsert_record(good)
    db.upsert_record(review)
    outputs = export_registry(config, db)
    assert outputs["summary"]["current_record_count"] == 1
    assert len(outputs["records"]) == 1
    assert (paths.site_data_dir / "records.json").exists()
    assert (paths.site_data_dir / "records.csv").exists()
    assert (paths.export_dir / "records.csv").exists()


def test_publication_validator_accepts_consistent_export(tmp_path: Path):
    paths = RepositoryPaths(
        root=tmp_path,
        db=tmp_path / "state/registry.sqlite",
        raw_dir=tmp_path / "data/raw",
        export_dir=tmp_path / "data/export",
        site_data_dir=tmp_path / "site/data",
        cache_dir=tmp_path / "data/cache",
        review_queue=tmp_path / "state/review_queue.json",
    )
    paths.ensure()
    variables = {
        "x": {
            "id": "x",
            "class": "Economic",
            "name": "Test",
            "canonical_unit": "percent",
        }
    }
    sources = {
        "s": {
            "id": "s",
            "name": "Source",
            "publisher": "Publisher",
            "adapter": "test",
            "enabled": True,
            "publish_enabled": True,
            "required": False,
            "optional": True,
        }
    }
    config = RegistryConfig(paths, variables, sources, {"publication": {}}, {})
    db = RegistryDB(paths.db)
    db.initialize()
    db.sync_config(variables, sources)
    export_registry(config, db)

    assert validate_publication(config)["records"] == 0

    summary_path = paths.site_data_dir / "summary.json"
    summary = __import__("json").loads(summary_path.read_text())
    summary["current_record_count"] = 1
    summary_path.write_text(__import__("json").dumps(summary), encoding="utf-8")
    with __import__("pytest").raises(PublicationError):
        validate_publication(config)


def test_publication_validator_rejects_record_after_source_gate_is_disabled(tmp_path: Path):
    paths = RepositoryPaths(
        root=tmp_path,
        db=tmp_path / "state/registry.sqlite",
        raw_dir=tmp_path / "data/raw",
        export_dir=tmp_path / "data/export",
        site_data_dir=tmp_path / "site/data",
        cache_dir=tmp_path / "data/cache",
        review_queue=tmp_path / "state/review_queue.json",
    )
    paths.ensure()
    variables = {"x": {"id": "x", "class": "Economic", "name": "Test", "canonical_unit": "percent"}}
    sources = {
        "s": {
            "id": "s",
            "name": "Source",
            "publisher": "Publisher",
            "adapter": "test",
            "enabled": True,
            "publish_enabled": True,
            "required": False,
        }
    }
    config = RegistryConfig(paths, variables, sources, {"publication": {}}, {})
    db = RegistryDB(paths.db)
    db.initialize()
    db.sync_config(variables, sources)
    db.upsert_record(
        Record(
            variable_id="x",
            source_id="s",
            source_series_id="series",
            value=1,
            unit_original="percent",
            unit_canonical="percent",
            reference_period_start="2026-01-01",
            reference_period_end="2026-01-01",
        )
    )
    export_registry(config, db)
    config.sources["s"]["publish_enabled"] = False

    with __import__("pytest").raises(PublicationError, match="publication gate is disabled"):
        validate_publication(config)
