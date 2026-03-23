"""Tests for src/cli.py."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from src.airac import cycle_for_date
from src.cli import _resolve_cycle, cli
from src.config import Config, EaipConfig, NatsSrdConfig, SourcesConfig, VatsimSctConfig
from src.processing.excel_to_csv import ExcelValidationError
from src.sources.eaip_html import EaipFetchError
from src.sources.nats_srd import SrdFetchError
from src.sources.vatsim_sct import SctFetchError


@pytest.fixture(autouse=True)
def _clean_logging():
    """Remove file handlers added by _setup_logging between tests."""
    yield
    src_logger = logging.getLogger("src")
    for h in src_logger.handlers[:]:
        h.close()
        src_logger.removeHandler(h)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CYCLE_2602 = cycle_for_date(date(2026, 2, 19))
CYCLE_2603 = cycle_for_date(date(2026, 3, 19))


def _make_config(tmp_path: Path) -> Config:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return Config(
        workspace_base=workspace,
        sources=SourcesConfig(
            nats_srd=NatsSrdConfig(page_url="", sheet_name="Routes", notes_sheet="Notes"),
            vatsim_sct=VatsimSctConfig(url=""),
            eaip=EaipConfig(page_url="", files=()),
        ),
    )


# ---------------------------------------------------------------------------
# _resolve_cycle
# ---------------------------------------------------------------------------

class TestResolveCycle:
    def test_none_returns_current_cycle(self):
        with patch("src.cli.current_cycle", return_value=CYCLE_2602):
            assert _resolve_cycle(None) == CYCLE_2602

    def test_valid_ident_returns_correct_cycle(self):
        result = _resolve_cycle("2602")
        assert result.ident == "2602"

    def test_valid_ident_2603(self):
        result = _resolve_cycle("2603")
        assert result.ident == "2603"

    def test_non_numeric_raises(self):
        import click
        with pytest.raises(click.BadParameter):
            _resolve_cycle("ABCD")

    def test_wrong_length_raises(self):
        import click
        with pytest.raises(click.BadParameter):
            _resolve_cycle("260")

    def test_cycle_number_zero_raises(self):
        import click
        with pytest.raises(click.BadParameter):
            _resolve_cycle("2600")

    def test_cycle_number_14_raises(self):
        import click
        with pytest.raises(click.BadParameter):
            _resolve_cycle("2614")

    def test_five_digits_raises(self):
        import click
        with pytest.raises(click.BadParameter):
            _resolve_cycle("26034")


# ---------------------------------------------------------------------------
# fetch command
# ---------------------------------------------------------------------------

class TestFetchCommand:
    def _invoke(self, tmp_path: Path, args: list[str] | None = None) -> object:
        cfg = _make_config(tmp_path)
        runner = CliRunner()
        excel_path = tmp_path / "workspace" / "vFPC 2603" / "SRD.xlsx"

        with (
            patch("src.cli.load", return_value=cfg),
            patch("src.cli.ensure_cycle_dir"),
            patch("src.cli.copy_in_json_forward", return_value=None),
            patch("src.cli.fetch_eaip_html", return_value={"EG-ENR-3.2-en-GB.html": Path("EG-ENR-3.2-en-GB.html"), "EG-ENR-3.3-en-GB.html": Path("EG-ENR-3.3-en-GB.html")}),
            patch("src.cli.fetch_srd", return_value={"SRD.xlsx": excel_path}),
            patch("src.cli.convert_srd_excel", return_value={"Routes": Path("Routes.csv"), "Notes": Path("Notes.csv")}),
            patch("src.cli.fetch_sct", return_value=Path("UK_2026_03.sct")),
        ):
            return runner.invoke(cli, ["fetch", "--cycle", "2603"] + (args or []))

    def test_exits_zero_on_success(self, tmp_path):
        result = self._invoke(tmp_path)
        assert result.exit_code == 0

    def test_output_mentions_cycle_ident(self, tmp_path):
        result = self._invoke(tmp_path)
        assert "2603" in result.output

    def test_output_mentions_all_files_ready(self, tmp_path):
        result = self._invoke(tmp_path)
        assert "All files ready" in result.output

    def test_output_mentions_each_step(self, tmp_path):
        result = self._invoke(tmp_path)
        assert "eAIP" in result.output
        assert "SRD" in result.output
        assert "sector" in result.output.lower()

    def test_config_error_exits_nonzero(self, tmp_path):
        runner = CliRunner()
        from src.config import ConfigError
        with patch("src.cli.load", side_effect=ConfigError("missing key")):
            result = runner.invoke(cli, ["fetch", "--cycle", "2603"])
        assert result.exit_code != 0

    def test_invalid_cycle_ident_exits_nonzero(self, tmp_path):
        cfg = _make_config(tmp_path)
        runner = CliRunner()
        with patch("src.cli.load", return_value=cfg):
            result = runner.invoke(cli, ["fetch", "--cycle", "ABCD"])
        assert result.exit_code != 0

    def test_eaip_error_exits_nonzero(self, tmp_path):
        cfg = _make_config(tmp_path)
        runner = CliRunner()
        with (
            patch("src.cli.load", return_value=cfg),
            patch("src.cli.ensure_cycle_dir"),
            patch("src.cli.copy_in_json_forward", return_value=None),
            patch("src.cli.fetch_eaip_html", side_effect=EaipFetchError("page changed")),
        ):
            result = runner.invoke(cli, ["fetch", "--cycle", "2603"])
        assert result.exit_code != 0

    def test_srd_error_exits_nonzero(self, tmp_path):
        cfg = _make_config(tmp_path)
        runner = CliRunner()
        with (
            patch("src.cli.load", return_value=cfg),
            patch("src.cli.ensure_cycle_dir"),
            patch("src.cli.copy_in_json_forward", return_value=None),
            patch("src.cli.fetch_eaip_html", return_value={}),
            patch("src.cli.fetch_srd", side_effect=SrdFetchError("HTTP 404")),
        ):
            result = runner.invoke(cli, ["fetch", "--cycle", "2603"])
        assert result.exit_code != 0

    def test_excel_validation_error_exits_nonzero(self, tmp_path):
        cfg = _make_config(tmp_path)
        runner = CliRunner()
        excel_path = tmp_path / "SRD.xlsx"
        with (
            patch("src.cli.load", return_value=cfg),
            patch("src.cli.ensure_cycle_dir"),
            patch("src.cli.copy_in_json_forward", return_value=None),
            patch("src.cli.fetch_eaip_html", return_value={}),
            patch("src.cli.fetch_srd", return_value={"SRD.xlsx": excel_path}),
            patch("src.cli.convert_srd_excel", side_effect=ExcelValidationError("wrong cycle")),
        ):
            result = runner.invoke(cli, ["fetch", "--cycle", "2603"])
        assert result.exit_code != 0

    def test_sct_error_exits_nonzero(self, tmp_path):
        cfg = _make_config(tmp_path)
        runner = CliRunner()
        excel_path = tmp_path / "SRD.xlsx"
        with (
            patch("src.cli.load", return_value=cfg),
            patch("src.cli.ensure_cycle_dir"),
            patch("src.cli.copy_in_json_forward", return_value=None),
            patch("src.cli.fetch_eaip_html", return_value={}),
            patch("src.cli.fetch_srd", return_value={"SRD.xlsx": excel_path}),
            patch("src.cli.convert_srd_excel", return_value={}),
            patch("src.cli.fetch_sct", side_effect=SctFetchError("no release found")),
        ):
            result = runner.invoke(cli, ["fetch", "--cycle", "2603"])
        assert result.exit_code != 0

    def test_copy_forward_done_message_when_copied(self, tmp_path):
        cfg = _make_config(tmp_path)
        runner = CliRunner()
        excel_path = tmp_path / "SRD.xlsx"
        with (
            patch("src.cli.load", return_value=cfg),
            patch("src.cli.ensure_cycle_dir"),
            patch("src.cli.copy_in_json_forward", return_value=Path("in.json")),
            patch("src.cli.fetch_eaip_html", return_value={}),
            patch("src.cli.fetch_srd", return_value={"SRD.xlsx": excel_path}),
            patch("src.cli.convert_srd_excel", return_value={}),
            patch("src.cli.fetch_sct", return_value=Path("UK_2026_03.sct")),
        ):
            result = runner.invoke(cli, ["fetch", "--cycle", "2603"])
        assert "copied" in result.output

    def test_copy_forward_skipped_message_when_not_copied(self, tmp_path):
        result = self._invoke(tmp_path)
        assert "skipped" in result.output

    def test_default_cycle_used_when_no_option(self, tmp_path):
        cfg = _make_config(tmp_path)
        runner = CliRunner()
        excel_path = tmp_path / "SRD.xlsx"
        with (
            patch("src.cli.load", return_value=cfg),
            patch("src.cli.current_cycle", return_value=CYCLE_2603),
            patch("src.cli.ensure_cycle_dir"),
            patch("src.cli.copy_in_json_forward", return_value=None),
            patch("src.cli.fetch_eaip_html", return_value={}),
            patch("src.cli.fetch_srd", return_value={"SRD.xlsx": excel_path}),
            patch("src.cli.convert_srd_excel", return_value={}),
            patch("src.cli.fetch_sct", return_value=Path("UK_2026_03.sct")),
        ):
            result = runner.invoke(cli, ["fetch"])
        assert "2603" in result.output

    def test_eaip_page_url_from_config_passed_through(self, tmp_path):
        cfg = _make_config(tmp_path)
        cfg = Config(
            workspace_base=cfg.workspace_base,
            sources=SourcesConfig(
                nats_srd=NatsSrdConfig(page_url="", sheet_name="Routes", notes_sheet="Notes"),
                vatsim_sct=VatsimSctConfig(url=""),
                eaip=EaipConfig(page_url="https://custom.url/aip", files=()),
            ),
        )
        runner = CliRunner()
        excel_path = tmp_path / "SRD.xlsx"
        with (
            patch("src.cli.load", return_value=cfg),
            patch("src.cli.ensure_cycle_dir"),
            patch("src.cli.copy_in_json_forward", return_value=None),
            patch("src.cli.fetch_eaip_html", return_value={}) as mock_eaip,
            patch("src.cli.fetch_srd", return_value={"SRD.xlsx": excel_path}),
            patch("src.cli.convert_srd_excel", return_value={}),
            patch("src.cli.fetch_sct", return_value=Path("UK_2026_03.sct")),
        ):
            runner.invoke(cli, ["fetch", "--cycle", "2603"])
        _, kwargs = mock_eaip.call_args
        assert kwargs.get("index_url") == "https://custom.url/aip"

    def test_empty_eaip_page_url_not_passed_through(self, tmp_path):
        cfg = _make_config(tmp_path)
        runner = CliRunner()
        excel_path = tmp_path / "SRD.xlsx"
        with (
            patch("src.cli.load", return_value=cfg),
            patch("src.cli.ensure_cycle_dir"),
            patch("src.cli.copy_in_json_forward", return_value=None),
            patch("src.cli.fetch_eaip_html", return_value={}) as mock_eaip,
            patch("src.cli.fetch_srd", return_value={"SRD.xlsx": excel_path}),
            patch("src.cli.convert_srd_excel", return_value={}),
            patch("src.cli.fetch_sct", return_value=Path("UK_2026_03.sct")),
        ):
            runner.invoke(cli, ["fetch", "--cycle", "2603"])
        _, kwargs = mock_eaip.call_args
        assert "index_url" not in kwargs

    def test_log_file_created_on_success(self, tmp_path):
        result = self._invoke(tmp_path)
        assert result.exit_code == 0
        work_dir = tmp_path / "workspace" / "vFPC 2603"
        log_files = list(work_dir.glob("fetcher_log_*.txt"))
        assert len(log_files) == 1

    def test_log_file_contains_cycle_info(self, tmp_path):
        self._invoke(tmp_path)
        work_dir = tmp_path / "workspace" / "vFPC 2603"
        log_files = list(work_dir.glob("fetcher_log_*.txt"))
        content = log_files[0].read_text(encoding="utf-8")
        assert "2603" in content
        assert "run started" in content
        assert "run complete" in content

    def test_output_shows_log_file_path(self, tmp_path):
        result = self._invoke(tmp_path)
        assert "Log file:" in result.output
        assert "fetcher_log_" in result.output

    def test_repeated_fetch_does_not_duplicate_handlers(self, tmp_path):
        """Two fetch invocations must not accumulate file handlers."""
        self._invoke(tmp_path)
        self._invoke(tmp_path)
        src_logger = logging.getLogger("src")
        assert len(src_logger.handlers) <= 1

    def test_repeated_fetch_creates_separate_log_files(self, tmp_path):
        self._invoke(tmp_path)
        self._invoke(tmp_path)
        work_dir = tmp_path / "workspace" / "vFPC 2603"
        log_files = list(work_dir.glob("fetcher_log_*.txt"))
        assert len(log_files) >= 1


# ---------------------------------------------------------------------------
# Top-level help
# ---------------------------------------------------------------------------

class TestCliHelp:
    def test_help_exits_zero(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0

    def test_fetch_help_exits_zero(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["fetch", "--help"])
        assert result.exit_code == 0

    def test_fetch_in_help_output(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "fetch" in result.output
