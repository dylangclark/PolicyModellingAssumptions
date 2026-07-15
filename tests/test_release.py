from datetime import UTC, datetime
from pathlib import Path

from bc_assumptions.config import RegistryConfig, RepositoryPaths
from bc_assumptions.db import RegistryDB
from bc_assumptions.models import Record, RunSummary
from bc_assumptions.pipeline import Pipeline
from bc_assumptions.release import (
    coverage_blockers_for_source,
    iter_coverage_requirements,
    release_blockers,
)


def _config(tmp_path: Path) -> RegistryConfig:
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
            "name": "X",
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
            "required": True,
            "optional": False,
            "collection_stale_after_days": 14,
            "stale_after_days": 30,
            "series": [
                {
                    "source_series_id": "series",
                    "variable_id": "x",
                    "unit_original": "percent",
                    "unit_canonical": "percent",
                }
            ],
        }
    }
    return RegistryConfig(paths, variables, sources, {"publication": {}}, {})


def test_release_gate_requires_successful_run_and_fresh_coverage(tmp_path: Path):
    config = _config(tmp_path)
    db = RegistryDB(config.paths.db)
    db.initialize()
    db.sync_config(config.variables, config.sources)

    assert any("no collection run" in item for item in release_blockers(config, db))
    assert any("missing required series" in item for item in release_blockers(config, db))

    db.upsert_record(
        Record(
            variable_id="x",
            source_id="s",
            source_series_id="series",
            value=1.0,
            unit_original="percent",
            unit_canonical="percent",
            reference_period_start="2026-07-01",
            reference_period_end="2026-07-01",
        )
    )
    run_id = db.start_run("s")
    db.finish_run(RunSummary(run_id=run_id, source_id="s", status="success"))

    blockers = release_blockers(
        config,
        db,
        as_of=datetime(2026, 7, 13, tzinfo=UTC),
    )
    assert blockers == []


def test_coverage_gate_detects_stale_series(tmp_path: Path):
    config = _config(tmp_path)
    db = RegistryDB(config.paths.db)
    db.initialize()
    db.sync_config(config.variables, config.sources)
    db.upsert_record(
        Record(
            variable_id="x",
            source_id="s",
            source_series_id="series",
            value=1.0,
            unit_original="percent",
            unit_canonical="percent",
            reference_period_start="2025-01-01",
            reference_period_end="2025-01-01",
        )
    )
    blockers = coverage_blockers_for_source(
        config.sources["s"],
        db,
        as_of=datetime(2026, 7, 13, tzinfo=UTC).date(),
    )
    assert len(blockers) == 1
    assert "stale series" in blockers[0]


def test_dataset_requirement_uses_adapter_series_identifier():
    source = {
        "id": "statcan",
        "stale_after_days": 90,
        "datasets": [
            {
                "dataset_id": "population",
                "product_id": "17100009",
                "outputs": [{"variable_id": "population"}],
            }
        ],
    }
    requirements = list(iter_coverage_requirements(source))
    assert requirements[0].source_series_id == "17100009:population"


def test_required_missing_api_key_is_failed_not_skipped(tmp_path: Path, monkeypatch):
    config = _config(tmp_path)
    source = config.sources["s"]
    source["api_key_env"] = "MISSING_TEST_KEY"
    monkeypatch.delenv("MISSING_TEST_KEY", raising=False)

    pipeline = Pipeline(config)
    pipeline.initialize()
    summary = pipeline._run_source(source, full_refresh=False)

    assert summary.status == "failed"
    assert summary.error == "Missing environment variable MISSING_TEST_KEY"


def test_review_required_record_makes_source_run_partial(tmp_path: Path, monkeypatch):
    from bc_assumptions.adapters import ADAPTERS
    from bc_assumptions.adapters.base import SourceAdapter
    from bc_assumptions.models import CollectionResult

    config = _config(tmp_path)
    config.variables["x"]["expected_max"] = 10

    class ReviewAdapter(SourceAdapter):
        def collect(self, full_refresh: bool = False) -> CollectionResult:
            return CollectionResult(
                source_id=self.source_id,
                records=[
                    Record(
                        variable_id="x",
                        source_id="s",
                        source_series_id="series",
                        value=20,
                        unit_original="percent",
                        unit_canonical="percent",
                        reference_period_start="2026-07-01",
                        reference_period_end="2026-07-01",
                    )
                ],
            )

    monkeypatch.setitem(ADAPTERS, "test", ReviewAdapter)
    pipeline = Pipeline(config)
    pipeline.initialize()

    summary = pipeline._run_source(config.sources["s"], full_refresh=False)

    assert summary.status == "partial"
    assert summary.records_rejected == 1
    assert any("requires review" in warning for warning in summary.warnings)


def test_dataset_can_be_excluded_from_required_coverage():
    from bc_assumptions.release import iter_coverage_requirements

    source = {
        "id": "example",
        "required": True,
        "datasets": [
            {
                "dataset_id": "required_dataset",
                "product_id": "100",
                "required": True,
                "outputs": [
                    {
                        "variable_id": "economic.required",
                    }
                ],
            },
            {
                "dataset_id": "non_required_dataset",
                "product_id": "200",
                "required": False,
                "outputs": [
                    {
                        "variable_id": "economic.non_required",
                    }
                ],
            },
        ],
    }

    requirements = list(iter_coverage_requirements(source))

    assert [
        (item.source_series_id, item.variable_id)
        for item in requirements
    ] == [
        ("100:required_dataset", "economic.required"),
    ]


def test_output_requirement_overrides_dataset_requirement():
    from bc_assumptions.release import iter_coverage_requirements

    source = {
        "id": "example",
        "required": True,
        "datasets": [
            {
                "dataset_id": "mixed_dataset",
                "product_id": "300",
                "required": False,
                "outputs": [
                    {
                        "variable_id": "economic.explicitly_required",
                        "required": True,
                    },
                    {
                        "variable_id": "economic.inherited_non_required",
                    },
                ],
            }
        ],
    }

    requirements = list(iter_coverage_requirements(source))

    assert [
        item.variable_id for item in requirements
    ] == [
        "economic.explicitly_required",
    ]
