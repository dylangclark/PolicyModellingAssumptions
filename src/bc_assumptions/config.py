from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any, Iterator

import yaml


class ConfigurationError(RuntimeError):
    pass


def find_repo_root(start: str | Path | None = None) -> Path:
    current = Path(start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "config").exists():
            return candidate
    raise ConfigurationError(
        f"Could not find repository root from {current}. Run from the repository or pass --root."
    )


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigurationError(f"Missing configuration file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigurationError(f"Expected a mapping in {path}")
    return data


def _resolve_path(root: Path, env_name: str, default: str) -> Path:
    raw = os.environ.get(env_name, default)
    path = Path(raw)
    return path if path.is_absolute() else root / path


@dataclass(frozen=True, slots=True)
class RepositoryPaths:
    root: Path
    db: Path
    raw_dir: Path
    export_dir: Path
    site_data_dir: Path
    cache_dir: Path
    review_queue: Path

    @classmethod
    def from_root(cls, root: Path) -> "RepositoryPaths":
        return cls(
            root=root,
            db=_resolve_path(root, "BC_ASSUMPTIONS_DB", "state/registry.sqlite"),
            raw_dir=_resolve_path(root, "BC_ASSUMPTIONS_RAW_DIR", "data/raw"),
            export_dir=_resolve_path(root, "BC_ASSUMPTIONS_EXPORT_DIR", "data/export"),
            site_data_dir=_resolve_path(root, "BC_ASSUMPTIONS_SITE_DATA_DIR", "site/data"),
            cache_dir=root / "data/cache",
            review_queue=root / "state/review_queue.json",
        )

    def ensure(self) -> None:
        for path in [
            self.db.parent,
            self.raw_dir,
            self.export_dir,
            self.site_data_dir,
            self.cache_dir,
            self.review_queue.parent,
        ]:
            path.mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class RegistryConfig:
    paths: RepositoryPaths
    variables: dict[str, dict[str, Any]]
    sources: dict[str, dict[str, Any]]
    validation: dict[str, Any]
    roadmap: dict[str, Any]

    @classmethod
    def load(cls, root: str | Path | None = None) -> "RegistryConfig":
        root_path = find_repo_root(root)
        paths = RepositoryPaths.from_root(root_path)
        paths.ensure()
        variable_rows = load_yaml(root_path / "config/variables.yml").get("variables", [])
        source_rows = load_yaml(root_path / "config/sources.yml").get("sources", [])
        if not isinstance(variable_rows, list) or not isinstance(source_rows, list):
            raise ConfigurationError("variables.yml and sources.yml must contain lists")
        variables = {row["id"]: row for row in variable_rows}
        sources = {row["id"]: row for row in source_rows}
        if len(variables) != len(variable_rows):
            raise ConfigurationError("Duplicate variable IDs in variables.yml")
        if len(sources) != len(source_rows):
            raise ConfigurationError("Duplicate source IDs in sources.yml")
        config = cls(
            paths=paths,
            variables=variables,
            sources=sources,
            validation=load_yaml(root_path / "config/validation_rules.yml"),
            roadmap=load_yaml(root_path / "config/roadmap.yml"),
        )
        config.validate()
        return config

    def validate(self) -> None:
        errors: list[str] = []
        try:
            from .adapters import ADAPTERS
        except ImportError:
            ADAPTERS = {}

        for variable_id, variable in self.variables.items():
            if variable.get("id") != variable_id:
                errors.append(f"Variable key and id differ: {variable_id}")
            for field in ("class", "name", "canonical_unit"):
                if not variable.get(field):
                    errors.append(f"Variable {variable_id} is missing {field}")
            minimum = variable.get("expected_min")
            maximum = variable.get("expected_max")
            if minimum is not None and maximum is not None and float(minimum) > float(maximum):
                errors.append(f"Variable {variable_id} has expected_min greater than expected_max")

        for source_id, source in self.sources.items():
            if source.get("id") != source_id:
                errors.append(f"Source key and id differ: {source_id}")
            for field in ("name", "publisher", "adapter"):
                if not source.get(field):
                    errors.append(f"Source {source_id} is missing {field}")
            for field in ("enabled", "publish_enabled", "optional", "required"):
                if field not in source or not isinstance(source[field], bool):
                    errors.append(f"Source {source_id} must define boolean {field}")
            if source.get("required") and source.get("optional"):
                errors.append(f"Source {source_id} cannot be both optional and required")
            if source.get("enabled") and source.get("required"):
                try:
                    collection_stale = int(source.get("collection_stale_after_days", 0))
                except (TypeError, ValueError):
                    collection_stale = 0
                if collection_stale <= 0:
                    errors.append(
                        f"Required source {source_id} must define a positive "
                        "collection_stale_after_days"
                    )
            if source.get("enabled") and source.get("adapter") not in ADAPTERS:
                errors.append(
                    f"Enabled source {source_id} uses unimplemented adapter "
                    f"{source.get('adapter')!r}"
                )

            output_count = 0
            for output in iter_source_outputs(source):
                output_count += 1
                variable_id = output.get("variable_id")
                if variable_id not in self.variables:
                    errors.append(f"Source {source_id} references unknown variable {variable_id}")
                    continue
                for field in ("unit_original", "unit_canonical"):
                    if not output.get(field):
                        errors.append(f"Source {source_id} output {variable_id} is missing {field}")
                expected_unit = self.variables[variable_id]["canonical_unit"]
                if output.get("unit_canonical") != expected_unit:
                    errors.append(
                        f"Source {source_id} output {variable_id} uses "
                        f"{output.get('unit_canonical')} instead of {expected_unit}"
                    )
            if source.get("enabled") and output_count == 0:
                errors.append(f"Enabled source {source_id} has no configured outputs")

            freshness_rows: list[dict[str, Any]] = [source]
            freshness_rows.extend(source.get("series", []))
            for dataset in source.get("datasets", []):
                freshness_rows.append(dataset)
                freshness_rows.extend(dataset.get("outputs", []))
                for series in dataset.get("series", []):
                    freshness_rows.append(series)
                    freshness_rows.extend(series.get("outputs", []))
            for row in freshness_rows:
                if "stale_after_days" not in row:
                    continue
                try:
                    stale_after = int(row["stale_after_days"])
                except (TypeError, ValueError):
                    stale_after = 0
                if stale_after <= 0:
                    errors.append(f"Source {source_id} has a non-positive stale_after_days value")

            if source.get("enabled") and source.get("required"):
                from .release import iter_coverage_requirements

                requirements = list(iter_coverage_requirements(source))
                for requirement in requirements:
                    if requirement.stale_after_days is None:
                        errors.append(
                            f"Required source {source_id} has no freshness limit for "
                            f"{requirement.source_series_id}/{requirement.variable_id}"
                        )

            selector_patterns: list[str] = []
            selectors: list[dict[str, Any]] = []
            for dataset in source.get("datasets", []):
                selectors.extend(dataset.get("selectors", []))
                selectors.extend(dataset.get("common_selectors", []))
                for series in dataset.get("series", []):
                    selectors.extend(series.get("selectors", []))
            for series in source.get("series", []):
                selector_patterns.extend(series.get("aliases", []))
            if source.get("sheet_regex"):
                selector_patterns.append(source["sheet_regex"])
            for pattern in selector_patterns:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    errors.append(f"Source {source_id} has invalid regex {pattern!r}: {exc}")

            for selector in selectors:
                for key in ("dimension", "member"):
                    try:
                        re.compile(selector[key])
                    except (KeyError, re.error) as exc:
                        errors.append(f"Source {source_id} has invalid selector {key}: {exc}")

        if errors:
            raise ConfigurationError("\n".join(errors))


def iter_source_outputs(source: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for series in source.get("series", []):
        if series.get("outputs"):
            yield from series["outputs"]
        elif series.get("variable_id"):
            yield series
    for dataset in source.get("datasets", []):
        yield from dataset.get("outputs", [])
        for series in dataset.get("series", []):
            yield from series.get("outputs", [])
    for key in ("monthly_trade_series", "monthly_price_series"):
        yield from source.get(key, [])
    for table in source.get("tables", []):
        yield from table.get("series", [])
    for document in source.get("documents", []):
        yield from document.get("series", [])
