import importlib.util
import json
from pathlib import Path

import yaml


def load_module(root: Path):
    path = root / "scripts" / "build_source_gap_report.py"
    spec = importlib.util.spec_from_file_location("build_source_gap_report", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_build_report_marks_public_data(tmp_path):
    root = Path(__file__).resolve().parents[1]
    module = load_module(root)
    variables = {"variables": [
        {"id": "a", "class": "Economic", "name": "A", "canonical_unit": "x", "geography_id": "CA-BC"},
        {"id": "b", "class": "Demand", "name": "B", "canonical_unit": "y", "geography_id": "CA-BC"},
    ]}
    candidates = {
        "source_families": {"source_b": {"publisher": "Publisher B", "source_url": "https://example.test"}},
        "variables": {"b": {"status": "source_identified", "priority": 1, "preferred_source": "source_b"}},
    }
    registry = {"records": [{"variable_id": "a"}]}
    report = module.build_report(variables, candidates, registry)
    rows = {row["variable_id"]: row for row in report["variables"]}
    assert rows["a"]["workflow_status"] == "data_available"
    assert rows["a"]["public_record_count"] == 1
    assert rows["b"]["workflow_status"] == "source_identified"
    assert rows["b"]["preferred_source_name"] == "Publisher B"


def test_patch_configuration_has_no_carbon_price():
    root = Path(__file__).resolve().parents[1]
    variables = yaml.safe_load((root / "config" / "variables.yml").read_text())
    ids = {item["id"] for item in variables["variables"]}
    assert "policy.carbon_price.cad_per_tco2e" not in ids


def test_candidate_references_are_valid():
    root = Path(__file__).resolve().parents[1]
    candidates = yaml.safe_load((root / "config" / "source_candidates.yml").read_text())
    families = candidates["source_families"]
    for variable_id, entry in candidates["variables"].items():
        source_id = entry.get("preferred_source")
        assert source_id in families, f"{variable_id} references missing source family {source_id}"
