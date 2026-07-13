from pathlib import Path

from types import SimpleNamespace

from bc_assumptions.cli import _is_blocking_summary, _load_dotenv


def test_load_dotenv_loads_simple_values_without_overriding_environment(
    tmp_path: Path, monkeypatch
):
    (tmp_path / "config").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (tmp_path / ".env").write_text(
        "# comment\n"
        "EIA_API_KEY='from-file'\n"
        "export BC_ASSUMPTIONS_CONTACT=operator@example.org\n"
        "PRESERVE_ME=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    monkeypatch.delenv("BC_ASSUMPTIONS_CONTACT", raising=False)
    monkeypatch.setenv("PRESERVE_ME", "from-process")

    _load_dotenv(tmp_path)

    assert __import__("os").environ["EIA_API_KEY"] == "from-file"
    assert __import__("os").environ["BC_ASSUMPTIONS_CONTACT"] == "operator@example.org"
    assert __import__("os").environ["PRESERVE_ME"] == "from-process"


class _ConfigStub:
    def __init__(self):
        self.sources = {
            "required": {"required": True, "optional": False},
            "optional": {"required": False, "optional": True},
        }


def test_required_skipped_source_blocks_publication():
    config = _ConfigStub()
    assert _is_blocking_summary(config, SimpleNamespace(source_id="required", status="skipped"))
    assert not _is_blocking_summary(config, SimpleNamespace(source_id="optional", status="skipped"))
    assert _is_blocking_summary(config, SimpleNamespace(source_id="optional", status="partial"))
