from __future__ import annotations

from .config import RegistryConfig
from .db import RegistryDB
from .export import export_registry


def build_site(config: RegistryConfig, db: RegistryDB | None = None) -> dict:
    """Refresh the static JSON consumed by the checked-in GitHub Pages application."""
    return export_registry(config, db=db)
