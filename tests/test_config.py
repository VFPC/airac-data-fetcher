"""Tests for src/config.py — config loading, merging, and validation."""

from pathlib import Path

import pytest

from src.config import Config, ConfigError, load

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

MINIMAL_YAML = """\
workspace_base: /work
archive_repo: /archive
sources:
  nats_srd:
    page_url: ""
    sheet_name: Routes
    notes_sheet: Notes
  vatsim_sct:
    url: ""
  eaip:
    page_url: ""
    files:
      - EG-ENR-3.2-en-GB.html
      - EG-ENR-3.3-en-GB.html
"""


@pytest.fixture
def cfg_file(tmp_path: Path) -> Path:
    f = tmp_path / "config.yaml"
    f.write_text(MINIMAL_YAML, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# Basic loading
# ---------------------------------------------------------------------------

class TestLoad:
    def test_returns_config(self, cfg_file):
        assert isinstance(load(cfg_file), Config)

    def test_workspace_base_is_path(self, cfg_file):
        cfg = load(cfg_file)
        assert isinstance(cfg.workspace_base, Path)
        assert cfg.workspace_base == Path("/work")

    def test_archive_repo_is_path(self, cfg_file):
        assert load(cfg_file).archive_repo == Path("/archive")

    def test_nats_srd_sheet_names(self, cfg_file):
        srd = load(cfg_file).sources.nats_srd
        assert srd.sheet_name == "Routes"  # [RULE:SRD-EXCEL-STRUCTURE]
        assert srd.notes_sheet == "Notes"

    def test_eaip_files_is_tuple(self, cfg_file):
        files = load(cfg_file).sources.eaip.files
        assert isinstance(files, tuple)
        assert files == ("EG-ENR-3.2-en-GB.html", "EG-ENR-3.3-en-GB.html")

    def test_empty_urls_are_allowed(self, cfg_file):
        cfg = load(cfg_file)
        assert cfg.sources.nats_srd.page_url == ""
        assert cfg.sources.vatsim_sct.url == ""
        assert cfg.sources.eaip.page_url == ""

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            load(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml_raises(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("{ bad yaml: [", encoding="utf-8")
        with pytest.raises(ConfigError, match="Failed to parse"):
            load(f)

    def test_empty_yaml_raises_on_required_keys(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("", encoding="utf-8")
        with pytest.raises(ConfigError):
            load(f)


# ---------------------------------------------------------------------------
# Local override merging
# ---------------------------------------------------------------------------

class TestLocalOverride:
    def test_local_overrides_workspace_base(self, cfg_file):
        cfg_file.with_name("config.local.yaml").write_text(
            "workspace_base: /local/work\n", encoding="utf-8"
        )
        assert load(cfg_file).workspace_base == Path("/local/work")

    def test_local_deep_merges_source_url(self, cfg_file):
        cfg_file.with_name("config.local.yaml").write_text(
            "sources:\n  nats_srd:\n    page_url: https://example.com\n",
            encoding="utf-8",
        )
        cfg = load(cfg_file)
        assert cfg.sources.nats_srd.page_url == "https://example.com"
        assert cfg.sources.nats_srd.sheet_name == "Routes"  # untouched by override

    def test_local_does_not_affect_other_sources(self, cfg_file):
        cfg_file.with_name("config.local.yaml").write_text(
            "sources:\n  vatsim_sct:\n    url: https://vatsim.example\n",
            encoding="utf-8",
        )
        cfg = load(cfg_file)
        assert cfg.sources.vatsim_sct.url == "https://vatsim.example"
        assert cfg.sources.nats_srd.sheet_name == "Routes"  # untouched

    def test_missing_local_file_is_ignored(self, cfg_file):
        cfg = load(cfg_file)
        assert cfg.workspace_base == Path("/work")

    def test_invalid_local_yaml_raises(self, cfg_file):
        cfg_file.with_name("config.local.yaml").write_text(
            "{ bad: [", encoding="utf-8"
        )
        with pytest.raises(ConfigError, match="Failed to parse"):
            load(cfg_file)

    def test_local_can_override_archive_repo(self, cfg_file):
        cfg_file.with_name("config.local.yaml").write_text(
            "archive_repo: /local/archive\n", encoding="utf-8"
        )
        assert load(cfg_file).archive_repo == Path("/local/archive")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_missing_workspace_base_raises(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("archive_repo: /archive\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="workspace_base"):
            load(f)

    def test_empty_workspace_base_raises(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("workspace_base: ''\narchive_repo: /archive\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="workspace_base"):
            load(f)

    def test_missing_archive_repo_raises(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("workspace_base: /work\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="archive_repo"):
            load(f)

    def test_empty_archive_repo_raises(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("workspace_base: /work\narchive_repo: ''\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="archive_repo"):
            load(f)

    def test_sources_section_is_optional(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("workspace_base: /work\narchive_repo: /archive\n", encoding="utf-8")
        cfg = load(f)
        assert cfg.sources.nats_srd.page_url == ""
        assert cfg.sources.eaip.files == ()


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_config_is_frozen(self, cfg_file):
        cfg = load(cfg_file)
        with pytest.raises((AttributeError, TypeError)):
            cfg.workspace_base = Path("/other")  # type: ignore[misc]

    def test_sources_is_frozen(self, cfg_file):
        cfg = load(cfg_file)
        with pytest.raises((AttributeError, TypeError)):
            cfg.sources.nats_srd = None  # type: ignore[misc]
