from __future__ import annotations

from pathlib import Path

import pytest

from bc_assumptions.db import RegistryDB
from bc_assumptions.models import Artifact


@pytest.fixture
def artifact(tmp_path: Path) -> Artifact:
    return Artifact(
        source_id="test_source",
        source_url="https://example.test/data",
        local_path="test_source/aa/data.json",
        content_type="application/json",
        retrieved_at="2026-07-13T12:00:00Z",
        sha256="a" * 64,
        size_bytes=123,
    )


@pytest.fixture
def db(tmp_path: Path) -> RegistryDB:
    database = RegistryDB(tmp_path / "registry.sqlite")
    database.initialize()
    return database
