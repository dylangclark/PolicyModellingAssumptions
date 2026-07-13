import pytest

from bc_assumptions.config import ConfigurationError, RegistryConfig


def test_enabled_source_requires_implemented_adapter(tmp_path):
    paths_root = tmp_path
    (paths_root / "config").mkdir()
    (paths_root / "pyproject.toml").write_text("[project]\nname='test'\n")
    (paths_root / "config/variables.yml").write_text(
        "variables:\n  - id: x\n    class: Economic\n    name: X\n    canonical_unit: percent\n"
    )
    (paths_root / "config/sources.yml").write_text(
        "sources:\n"
        "  - id: bad\n"
        "    name: Bad\n"
        "    publisher: Test\n"
        "    adapter: not_implemented\n"
        "    enabled: true\n"
        "    publish_enabled: true\n"
        "    series:\n"
        "      - source_series_id: x\n"
        "        variable_id: x\n"
        "        unit_original: percent\n"
        "        unit_canonical: percent\n"
    )
    (paths_root / "config/validation_rules.yml").write_text("publication: {}\n")
    (paths_root / "config/roadmap.yml").write_text("roadmap: {}\n")
    with pytest.raises(ConfigurationError, match="unimplemented adapter"):
        RegistryConfig.load(paths_root)


def test_source_cannot_be_optional_and_required(tmp_path):
    paths_root = tmp_path
    (paths_root / "config").mkdir()
    (paths_root / "pyproject.toml").write_text("[project]\nname='test'\n")
    (paths_root / "config/variables.yml").write_text(
        "variables:\n  - id: x\n    class: Economic\n    name: X\n    canonical_unit: percent\n"
    )
    (paths_root / "config/sources.yml").write_text(
        "sources:\n"
        "  - id: bad\n"
        "    name: Bad\n"
        "    publisher: Test\n"
        "    adapter: boc_valet\n"
        "    enabled: true\n"
        "    optional: true\n"
        "    required: true\n"
        "    publish_enabled: true\n"
        "    series:\n"
        "      - source_series_id: x\n"
        "        variable_id: x\n"
        "        unit_original: percent\n"
        "        unit_canonical: percent\n"
    )
    (paths_root / "config/validation_rules.yml").write_text("publication: {}\n")
    (paths_root / "config/roadmap.yml").write_text("roadmap: {}\n")
    with pytest.raises(ConfigurationError, match="cannot be both optional and required"):
        RegistryConfig.load(paths_root)
