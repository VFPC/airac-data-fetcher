"""Tests for src/cli.py."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from src.airac import cycle_for_date
from src.archive.archiver import ArchiverError
from src.cli import _resolve_cycle, cli
from src.config import Config, EaipConfig, NatsSrdConfig, SourcesConfig, VatsimSctConfig
from src.processing.excel_to_csv import ExcelValidationError
from src.sources.eaip_html import EaipFetchError
from src.sources.nats_srd import SrdFetchError
from src.sources.vatsim_sct import SctFetchError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CYCLE_2602 = cycle_for_date(date(2026, 2, 19))
CYCLE_2603 = cycle_for_date(date(2026, 3, 19))


def _make_config(tmp_path: Path) -> Config:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    archive = tmp_path / "airac-data"
    archive.mkdir(exist_ok=True)
    return Config(
        workspace_base=workspace,
        archive_repo=archive,
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
            archive_repo=cfg.archive_repo,
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


# ---------------------------------------------------------------------------
# archive command
# ---------------------------------------------------------------------------

class TestArchiveCommand:
    def _invoke(self, tmp_path: Path, archive_result=None) -> object:
        cfg = _make_config(tmp_path)
        runner = CliRunner()
        if archive_result is None:
            zip_p = cfg.archive_repo / "vFPC 2603" / "vFPC 2603.zip"
            manifest_p = cfg.archive_repo / "vFPC 2603" / "manifest.md"
            archive_result = (zip_p, manifest_p)
        with (
            patch("src.cli.load", return_value=cfg),
            patch("src.cli.archive_cycle", return_value=archive_result),
        ):
            return runner.invoke(cli, ["archive", "--cycle", "2603"])

    def test_exits_zero_on_success(self, tmp_path):
        result = self._invoke(tmp_path)
        assert result.exit_code == 0

    def test_output_mentions_cycle_ident(self, tmp_path):
        result = self._invoke(tmp_path)
        assert "2603" in result.output

    def test_output_mentions_staged(self, tmp_path):
        result = self._invoke(tmp_path)
        assert "Staged" in result.output

    def test_output_mentions_commit(self, tmp_path):
        result = self._invoke(tmp_path)
        assert "commit" in result.output.lower()

    def test_shows_zip_path(self, tmp_path):
        cfg = _make_config(tmp_path)
        zip_p = cfg.archive_repo / "vFPC 2603" / "vFPC 2603.zip"
        manifest_p = cfg.archive_repo / "vFPC 2603" / "manifest.md"
        result = self._invoke(tmp_path, archive_result=(zip_p, manifest_p))
        assert "vFPC 2603.zip" in result.output

    def test_archiver_error_exits_nonzero(self, tmp_path):
        cfg = _make_config(tmp_path)
        runner = CliRunner()
        with (
            patch("src.cli.load", return_value=cfg),
            patch("src.cli.archive_cycle", side_effect=ArchiverError("out.json missing")),
        ):
            result = runner.invoke(cli, ["archive", "--cycle", "2603"])
        assert result.exit_code != 0

    def test_archiver_error_message_shown(self, tmp_path):
        cfg = _make_config(tmp_path)
        runner = CliRunner()
        with (
            patch("src.cli.load", return_value=cfg),
            patch("src.cli.archive_cycle", side_effect=ArchiverError("out.json missing")),
        ):
            result = runner.invoke(cli, ["archive", "--cycle", "2603"])
        assert "out.json missing" in result.output

    def test_config_error_exits_nonzero(self, tmp_path):
        from src.config import ConfigError
        runner = CliRunner()
        with patch("src.cli.load", side_effect=ConfigError("missing archive_repo")):
            result = runner.invoke(cli, ["archive", "--cycle", "2603"])
        assert result.exit_code != 0

    def test_default_cycle_used_when_no_option(self, tmp_path):
        cfg = _make_config(tmp_path)
        runner = CliRunner()
        zip_p = cfg.archive_repo / "vFPC 2602" / "vFPC 2602.zip"
        manifest_p = cfg.archive_repo / "vFPC 2602" / "manifest.md"
        with (
            patch("src.cli.load", return_value=cfg),
            patch("src.cli.current_cycle", return_value=CYCLE_2602),
            patch("src.cli.archive_cycle", return_value=(zip_p, manifest_p)),
        ):
            result = runner.invoke(cli, ["archive"])
        assert "2602" in result.output

    def test_archive_cycle_called_with_correct_args(self, tmp_path):
        cfg = _make_config(tmp_path)
        runner = CliRunner()
        zip_p = cfg.archive_repo / "vFPC 2603" / "vFPC 2603.zip"
        manifest_p = cfg.archive_repo / "vFPC 2603" / "manifest.md"
        with (
            patch("src.cli.load", return_value=cfg),
            patch("src.cli.archive_cycle", return_value=(zip_p, manifest_p)) as mock_archive,
        ):
            runner.invoke(cli, ["archive", "--cycle", "2603"])
        args = mock_archive.call_args[0]
        assert args[0].ident == "2603"
        assert args[2] == cfg.archive_repo


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

    def test_archive_help_exits_zero(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["archive", "--help"])
        assert result.exit_code == 0

    def test_fetch_in_help_output(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "fetch" in result.output

    def test_archive_in_help_output(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "archive" in result.output
