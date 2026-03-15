"""Tests for src/workspace/directory_manager.py."""

from datetime import date
from pathlib import Path

import pytest

from src.airac import cycle_for_date
from src.workspace.directory_manager import (
    copy_in_json_forward,
    cycle_dir,
    ensure_cycle_dir,
)

# Two consecutive real cycles used throughout.
CYCLE_2602 = cycle_for_date(date(2026, 2, 19))  # effective 2026-02-19
CYCLE_2601 = cycle_for_date(date(2026, 1, 22))  # effective 2026-01-22  (prev of 2602)


# ---------------------------------------------------------------------------
# cycle_dir
# ---------------------------------------------------------------------------

class TestCycleDir:
    def test_returns_path(self, tmp_path):
        assert isinstance(cycle_dir(tmp_path, CYCLE_2602), Path)

    def test_naming_convention(self, tmp_path):
        assert cycle_dir(tmp_path, CYCLE_2602).name == "vFPC 2602"

    def test_parent_is_workspace_base(self, tmp_path):
        assert cycle_dir(tmp_path, CYCLE_2602).parent == tmp_path

    def test_different_cycles_different_dirs(self, tmp_path):
        assert cycle_dir(tmp_path, CYCLE_2602) != cycle_dir(tmp_path, CYCLE_2601)

    def test_does_not_create_directory(self, tmp_path):
        path = cycle_dir(tmp_path, CYCLE_2602)
        assert not path.exists()


# ---------------------------------------------------------------------------
# ensure_cycle_dir
# ---------------------------------------------------------------------------

class TestEnsureCycleDir:
    def test_creates_directory(self, tmp_path):
        path = ensure_cycle_dir(tmp_path, CYCLE_2602)
        assert path.exists()
        assert path.is_dir()

    def test_returns_correct_path(self, tmp_path):
        path = ensure_cycle_dir(tmp_path, CYCLE_2602)
        assert path == cycle_dir(tmp_path, CYCLE_2602)

    def test_idempotent(self, tmp_path):
        ensure_cycle_dir(tmp_path, CYCLE_2602)
        ensure_cycle_dir(tmp_path, CYCLE_2602)  # second call must not raise
        assert cycle_dir(tmp_path, CYCLE_2602).is_dir()

    def test_creates_intermediate_directories(self, tmp_path):
        nested_base = tmp_path / "a" / "b"
        path = ensure_cycle_dir(nested_base, CYCLE_2602)
        assert path.is_dir()

    def test_does_not_disturb_existing_files(self, tmp_path):
        path = ensure_cycle_dir(tmp_path, CYCLE_2602)
        sentinel = path / "sentinel.txt"
        sentinel.write_text("keep me", encoding="utf-8")
        ensure_cycle_dir(tmp_path, CYCLE_2602)
        assert sentinel.read_text(encoding="utf-8") == "keep me"


# ---------------------------------------------------------------------------
# copy_in_json_forward
# ---------------------------------------------------------------------------

class TestCopyInJsonForward:
    def _make_prev_in_json(self, workspace: Path, content: str = "{}") -> Path:
        """Write in.json into the 2601 (previous) cycle directory."""
        prev_dir = cycle_dir(workspace, CYCLE_2601)
        prev_dir.mkdir(parents=True, exist_ok=True)
        src = prev_dir / "in.json"
        src.write_text(content, encoding="utf-8")
        return src

    def test_copies_file_when_dest_missing(self, tmp_path):
        self._make_prev_in_json(tmp_path, '{"test": true}')
        ensure_cycle_dir(tmp_path, CYCLE_2602)
        result = copy_in_json_forward(tmp_path, CYCLE_2602)
        assert result is not None
        assert result.exists()

    def test_returns_destination_path(self, tmp_path):
        self._make_prev_in_json(tmp_path)
        ensure_cycle_dir(tmp_path, CYCLE_2602)
        result = copy_in_json_forward(tmp_path, CYCLE_2602)
        assert result == cycle_dir(tmp_path, CYCLE_2602) / "in.json"

    def test_content_is_preserved(self, tmp_path):
        payload = '{"cycle": "2601", "data": 42}'
        self._make_prev_in_json(tmp_path, payload)
        ensure_cycle_dir(tmp_path, CYCLE_2602)
        copy_in_json_forward(tmp_path, CYCLE_2602)
        dest = cycle_dir(tmp_path, CYCLE_2602) / "in.json"
        assert dest.read_text(encoding="utf-8") == payload

    def test_does_not_overwrite_existing_in_json(self, tmp_path):
        self._make_prev_in_json(tmp_path, '{"from": "prev"}')
        dest_dir = ensure_cycle_dir(tmp_path, CYCLE_2602)
        existing = dest_dir / "in.json"
        existing.write_text('{"from": "current"}', encoding="utf-8")
        result = copy_in_json_forward(tmp_path, CYCLE_2602)
        assert result is None
        assert existing.read_text(encoding="utf-8") == '{"from": "current"}'

    def test_returns_none_when_prev_dir_missing(self, tmp_path):
        ensure_cycle_dir(tmp_path, CYCLE_2602)
        assert copy_in_json_forward(tmp_path, CYCLE_2602) is None

    def test_returns_none_when_prev_in_json_missing(self, tmp_path):
        # Create prev dir but without in.json
        cycle_dir(tmp_path, CYCLE_2601).mkdir(parents=True)
        ensure_cycle_dir(tmp_path, CYCLE_2602)
        assert copy_in_json_forward(tmp_path, CYCLE_2602) is None

    def test_creates_dest_dir_if_needed(self, tmp_path):
        self._make_prev_in_json(tmp_path)
        # Do NOT call ensure_cycle_dir first — copy_in_json_forward must handle it
        result = copy_in_json_forward(tmp_path, CYCLE_2602)
        assert result is not None
        assert result.exists()

    def test_copy_uses_correct_previous_cycle(self, tmp_path):
        """The previous cycle of 2602 must be 2601, not some other cycle."""
        self._make_prev_in_json(tmp_path, '{"marker": "2601"}')
        copy_in_json_forward(tmp_path, CYCLE_2602)
        dest = cycle_dir(tmp_path, CYCLE_2602) / "in.json"
        assert '"marker": "2601"' in dest.read_text(encoding="utf-8")

    def test_year_boundary_copy(self, tmp_path):
        """Copy forward across a year boundary: 2313 → 2401."""
        cycle_2401 = cycle_for_date(date(2024, 1, 25))
        cycle_2313 = cycle_for_date(date(2023, 12, 28))

        prev_dir = cycle_dir(tmp_path, cycle_2313)
        prev_dir.mkdir(parents=True)
        (prev_dir / "in.json").write_text('{"year_boundary": true}', encoding="utf-8")

        result = copy_in_json_forward(tmp_path, cycle_2401)
        assert result is not None
        assert "year_boundary" in result.read_text(encoding="utf-8")
