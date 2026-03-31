"""Unit tests for src/sources/eaip_html.py.

All tests are offline: HTTP is replaced by injected callables or patched
functions.  No real network calls are made.  All filesystem writes go
through pytest's tmp_path fixture.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import call, patch

import pytest
from bs4 import BeautifulSoup

from src.airac import AiracCycle
from src.sources.eaip_html import (
    EaipFetchError,
    _cycle_heading_text,
    _extract_ad2_pages,
    _extract_all,
    _extract_targets,
    _find_download_url,
    _validate_effective_date,
    fetch_eaip_html,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CYCLE_2602 = AiracCycle(
    year=2026,
    number=2,
    effective_date=date(2026, 2, 19),
    expiry_date=date(2026, 3, 18),
)

_BASE_URL = "https://nats-uk.ead-it.com/cms-nats/opencms/en/Publication/AIP/"

ENR32_NAME = "EG-ENR-3.2-en-GB.html"
ENR33_NAME = "EG-ENR-3.3-en-GB.html"
ENR41_NAME = "EG-ENR-4.1-en-GB.html"
ENR42_NAME = "EG-ENR-4.2-en-GB.html"
ENR44_NAME = "EG-ENR-4.4-en-GB.html"

ALL_REQUIRED = {ENR32_NAME, ENR33_NAME, ENR41_NAME, ENR42_NAME, ENR44_NAME}

EGEL_AD2_NAME = "EG-AD-2.EGEL-en-GB.html"
EGLL_AD2_NAME = "EG-AD-2.EGLL-en-GB.html"


def _make_meta_html(effective_date: date) -> str:
    """Minimal eAIP HTML containing the EM.effectiveDateStart meta tag."""
    return (
        "<!DOCTYPE html><html><head>"
        f'<meta name="EM.effectiveDateStart" content="{effective_date.isoformat()}">'
        "</head><body></body></html>"
    )


def _make_zip(files: dict[str, bytes]) -> io.BytesIO:
    """Build an in-memory zip containing *files* {name: content}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    buf.seek(0)
    return buf


def _make_index_html(
    cycle: AiracCycle,
    download_url: str,
    heading_text: str | None = None,
    link_text: str = "Offline HTML Download",
) -> str:
    """Build a minimal AIP index page for *cycle*.

    # [RULE:EAIP-PAGE-STRUCTURE]
    """
    heading = heading_text or _cycle_heading_text(cycle)
    return (
        "<html><body>"
        f"<h3>{heading}</h3>"
        f"<h6>19 February 2026</h6>"
        f'<p><a href="{download_url}">{link_text}</a></p>'
        "</body></html>"
    )


# ---------------------------------------------------------------------------
# _cycle_heading_text
# ---------------------------------------------------------------------------

class TestCycleHeadingText:
    def test_format_mid_year(self):
        # [RULE:EAIP-PAGE-STRUCTURE] heading must be "AIRAC NN/YYYY"
        assert _cycle_heading_text(CYCLE_2602) == "AIRAC 02/2026"

    def test_format_first_cycle(self):
        c = AiracCycle(year=2025, number=1, effective_date=date(2025, 1, 23), expiry_date=date(2025, 2, 19))
        assert _cycle_heading_text(c) == "AIRAC 01/2025"

    def test_format_cycle_13(self):
        c = AiracCycle(year=2025, number=13, effective_date=date(2025, 12, 25), expiry_date=date(2026, 1, 21))
        assert _cycle_heading_text(c) == "AIRAC 13/2025"


# ---------------------------------------------------------------------------
# _find_download_url
# ---------------------------------------------------------------------------

class TestFindDownloadUrl:
    def test_absolute_url_returned_unchanged(self):
        expected = "https://example.com/aip-2602.zip"
        page = _make_index_html(CYCLE_2602, expected)
        url = _find_download_url(page, CYCLE_2602, _BASE_URL)
        assert url == expected

    def test_relative_url_resolved_against_base(self):
        page = _make_index_html(CYCLE_2602, "/downloads/aip-2602.zip")
        url = _find_download_url(page, CYCLE_2602, _BASE_URL)
        assert url == "https://nats-uk.ead-it.com/downloads/aip-2602.zip"

    def test_heading_not_found_raises(self):
        page = "<html><body><h3>AIRAC 99/1999</h3></body></html>"
        with pytest.raises(EaipFetchError, match="AIRAC 02/2026"):
            _find_download_url(page, CYCLE_2602, _BASE_URL)

    def test_link_not_found_raises(self):
        page = _make_index_html(CYCLE_2602, "https://example.com/x.zip", link_text="Wrong text")
        with pytest.raises(EaipFetchError, match="Offline HTML Download"):
            _find_download_url(page, CYCLE_2602, _BASE_URL)

    def test_stops_at_next_heading(self):
        """The link from a different cycle must not be picked up."""
        next_cycle = AiracCycle(
            year=2026, number=3,
            effective_date=date(2026, 3, 19), expiry_date=date(2026, 4, 15),
        )
        page = (
            "<html><body>"
            f"<h3>{_cycle_heading_text(CYCLE_2602)}</h3>"
            f"<h3>{_cycle_heading_text(next_cycle)}</h3>"
            '<p><a href="https://example.com/wrong.zip">Offline HTML Download</a></p>'
            "</body></html>"
        )
        with pytest.raises(EaipFetchError, match="Offline HTML Download"):
            _find_download_url(page, CYCLE_2602, _BASE_URL)

    def test_multiple_cycles_picks_correct_one(self):
        prev = AiracCycle(
            year=2026, number=1,
            effective_date=date(2026, 1, 22), expiry_date=date(2026, 2, 18),
        )
        page = (
            "<html><body>"
            f"<h3>{_cycle_heading_text(prev)}</h3>"
            '<p><a href="https://example.com/2601.zip">Offline HTML Download</a></p>'
            f"<h3>{_cycle_heading_text(CYCLE_2602)}</h3>"
            '<p><a href="https://example.com/2602.zip">Offline HTML Download</a></p>'
            "</body></html>"
        )
        url = _find_download_url(page, CYCLE_2602, _BASE_URL)
        assert url == "https://example.com/2602.zip"


# ---------------------------------------------------------------------------
# _extract_targets
# ---------------------------------------------------------------------------

def _make_required_zip(extra: dict[str, bytes] | None = None) -> io.BytesIO:
    """Build a zip containing all five required ENR files plus any extras."""
    files = {name: f"<html>{name}</html>".encode() for name in ALL_REQUIRED}
    if extra:
        files.update(extra)
    return _make_zip(files)


class TestExtractTargets:
    def test_extracts_all_required_files(self, tmp_path):
        content32 = b"<html>enr32</html>"
        content41 = b"<html>enr41</html>"
        buf = _make_zip({
            ENR32_NAME: content32,
            ENR33_NAME: b"<html>enr33</html>",
            ENR41_NAME: content41,
            ENR42_NAME: b"<html>enr42</html>",
            ENR44_NAME: b"<html>enr44</html>",
        })
        result = _extract_targets(buf, tmp_path)
        assert set(result.keys()) == ALL_REQUIRED
        assert result[ENR32_NAME].read_bytes() == content32
        assert result[ENR41_NAME].read_bytes() == content41

    def test_files_extracted_into_dest_dir(self, tmp_path):
        buf = _make_required_zip()
        result = _extract_targets(buf, tmp_path)
        for path in result.values():
            assert path.parent == tmp_path

    def test_located_by_basename_in_nested_path(self, tmp_path):
        """Files nested inside zip subdirectories are still found."""
        buf = _make_zip({
            f"deep/nested/path/{ENR32_NAME}": b"32",
            f"another/level/{ENR33_NAME}": b"33",
            f"eAIP/{ENR41_NAME}": b"41",
            f"eAIP/{ENR42_NAME}": b"42",
            f"eAIP/{ENR44_NAME}": b"44",
        })
        result = _extract_targets(buf, tmp_path)
        assert set(result.keys()) == ALL_REQUIRED

    def test_missing_enr41_raises(self, tmp_path):
        buf = _make_zip({ENR32_NAME: b"a", ENR33_NAME: b"b", ENR42_NAME: b"c"})
        with pytest.raises(EaipFetchError, match=ENR41_NAME):
            _extract_targets(buf, tmp_path)

    def test_all_missing_raises(self, tmp_path):
        buf = _make_zip({"unrelated.html": b"nothing"})
        with pytest.raises(EaipFetchError, match="missing expected files"):
            _extract_targets(buf, tmp_path)

    def test_extra_files_in_zip_are_ignored(self, tmp_path):
        buf = _make_required_zip({"EG-ENR-2.1-en-GB.html": b"ignore me"})
        result = _extract_targets(buf, tmp_path)
        assert set(result.keys()) == ALL_REQUIRED
        assert not (tmp_path / "EG-ENR-2.1-en-GB.html").exists()

    def test_no_partial_files_on_missing_target(self, tmp_path):
        """When one target is missing, others must NOT be left in dest_dir."""
        buf = _make_zip({ENR32_NAME: b"only one"})
        with pytest.raises(EaipFetchError):
            _extract_targets(buf, tmp_path)
        assert not (tmp_path / ENR32_NAME).exists()

    def test_temp_dir_cleaned_up_on_success(self, tmp_path):
        buf = _make_required_zip()
        _extract_targets(buf, tmp_path)
        remaining = [p for p in tmp_path.iterdir() if p.name.startswith(".eaip_tmp_")]
        assert remaining == []

    def test_temp_dir_cleaned_up_on_failure(self, tmp_path):
        buf = _make_zip({"unrelated.html": b"nothing"})
        with pytest.raises(EaipFetchError):
            _extract_targets(buf, tmp_path)
        remaining = [p for p in tmp_path.iterdir() if p.name.startswith(".eaip_tmp_")]
        assert remaining == []

    def test_rollback_committed_files_on_move_failure(self, tmp_path):
        """If any move fails, all previously committed files must be removed."""
        import shutil as _shutil
        buf = _make_required_zip()
        call_count = 0

        def fail_on_second(src, dst):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise OSError("simulated move failure")
            _shutil.move(src, dst)

        with patch("src.sources.eaip_html.shutil.move", side_effect=fail_on_second):
            with pytest.raises(OSError, match="simulated move failure"):
                _extract_targets(buf, tmp_path)

        for name in ALL_REQUIRED:
            assert not (tmp_path / name).exists()


# ---------------------------------------------------------------------------
# _extract_ad2_pages
# ---------------------------------------------------------------------------

class TestExtractAd2Pages:
    def test_extracts_matching_files_to_ad2_subdir(self, tmp_path):
        buf = _make_required_zip({
            EGEL_AD2_NAME: b"<html>egel</html>",
            EGLL_AD2_NAME: b"<html>egll</html>",
        })
        result = _extract_ad2_pages(buf, tmp_path)
        assert set(result.keys()) == {EGEL_AD2_NAME, EGLL_AD2_NAME}
        for path in result.values():
            assert path.parent == tmp_path / "ad2"

    def test_creates_ad2_subdir(self, tmp_path):
        buf = _make_required_zip({EGEL_AD2_NAME: b"<html/>"})
        _extract_ad2_pages(buf, tmp_path)
        assert (tmp_path / "ad2").is_dir()

    def test_no_ad2_files_returns_empty(self, tmp_path):
        buf = _make_required_zip()
        result = _extract_ad2_pages(buf, tmp_path)
        assert result == {}

    def test_ignores_non_ad2_files(self, tmp_path):
        buf = _make_required_zip({
            EGEL_AD2_NAME: b"<html>egel</html>",
            "EG-ENR-2.1-en-GB.html": b"not ad2",
        })
        result = _extract_ad2_pages(buf, tmp_path)
        assert set(result.keys()) == {EGEL_AD2_NAME}
        assert not (tmp_path / "ad2" / "EG-ENR-2.1-en-GB.html").exists()

    def test_located_by_basename_in_nested_path(self, tmp_path):
        buf = _make_zip({f"html/eAIP/{EGEL_AD2_NAME}": b"<html>egel</html>"})
        result = _extract_ad2_pages(buf, tmp_path)
        assert EGEL_AD2_NAME in result
        assert result[EGEL_AD2_NAME].read_bytes() == b"<html>egel</html>"

    def test_temp_dir_cleaned_up_on_success(self, tmp_path):
        buf = _make_required_zip({EGEL_AD2_NAME: b"<html/>"})
        _extract_ad2_pages(buf, tmp_path)
        remaining = [p for p in tmp_path.iterdir() if p.name.startswith(".ad2_tmp_")]
        assert remaining == []


# ---------------------------------------------------------------------------
# _extract_all — whole-operation atomicity
# ---------------------------------------------------------------------------

class TestExtractAll:
    def test_extracts_enr_and_ad2_together(self, tmp_path):
        buf = _make_required_zip({EGEL_AD2_NAME: b"<html>egel</html>"})
        result, ad2_count = _extract_all(buf, tmp_path)
        assert ALL_REQUIRED.issubset(set(result.keys()))
        assert EGEL_AD2_NAME in result
        assert ad2_count == 1

    def test_ad2_goes_into_subdir(self, tmp_path):
        buf = _make_required_zip({EGEL_AD2_NAME: b"<html/>"})
        result, _ = _extract_all(buf, tmp_path)
        assert result[EGEL_AD2_NAME].parent == tmp_path / "ad2"

    def test_ad2_subdir_not_created_when_no_ad2_files(self, tmp_path):
        buf = _make_required_zip()
        _extract_all(buf, tmp_path)
        assert not (tmp_path / "ad2").exists()

    def test_missing_required_file_leaves_no_enr_files(self, tmp_path):
        """If a required ENR file is absent, no files must be written at all."""
        buf = _make_zip({ENR32_NAME: b"a", ENR33_NAME: b"b", EGEL_AD2_NAME: b"c"})
        with pytest.raises(EaipFetchError, match="missing expected files"):
            _extract_all(buf, tmp_path)
        # Neither ENR files nor ad2/ must exist
        for name in [ENR32_NAME, ENR33_NAME]:
            assert not (tmp_path / name).exists()
        assert not (tmp_path / "ad2").exists()

    def test_move_failure_during_ad2_removes_created_ad2_dir(self, tmp_path):
        """If a move failure occurs after ad2/ was freshly created, ad2/ must be removed."""
        import shutil as _real_shutil
        buf = _make_required_zip({EGEL_AD2_NAME: b"<html/>"})
        original_move = _real_shutil.move

        def fail_on_ad2(src, dst):
            if Path(src).name == EGEL_AD2_NAME:
                raise OSError("simulated failure")
            original_move(src, dst)

        with patch("src.sources.eaip_html.shutil.move", side_effect=fail_on_ad2):
            with pytest.raises(OSError):
                _extract_all(buf, tmp_path)

        assert not (tmp_path / "ad2").exists()

    def test_move_failure_during_ad2_rolls_back_enr_files(self, tmp_path):
        """If an AD 2.2 move fails after ENR files were already committed,
        the ENR files must be rolled back too."""
        import shutil as _real_shutil
        buf = _make_required_zip({EGEL_AD2_NAME: b"<html/>"})

        original_move = _real_shutil.move

        def safe_fail_on_ad2(src, dst):
            if Path(src).name == EGEL_AD2_NAME:
                raise OSError("simulated AD2 move failure")
            original_move(src, dst)

        with patch("src.sources.eaip_html.shutil.move", side_effect=safe_fail_on_ad2):
            with pytest.raises(OSError, match="simulated AD2 move failure"):
                _extract_all(buf, tmp_path)

        # All ENR files that were moved must have been rolled back
        for name in ALL_REQUIRED:
            assert not (tmp_path / name).exists()


# ---------------------------------------------------------------------------
# _validate_effective_date
# ---------------------------------------------------------------------------

class TestValidateEffectiveDate:
    def test_matching_date_passes(self, tmp_path):
        f = tmp_path / ENR32_NAME
        f.write_text(_make_meta_html(CYCLE_2602.effective_date), encoding="utf-8")
        _validate_effective_date(f, CYCLE_2602.effective_date)  # should not raise

    def test_wrong_date_raises(self, tmp_path):
        f = tmp_path / ENR32_NAME
        f.write_text(_make_meta_html(date(2025, 1, 1)), encoding="utf-8")
        with pytest.raises(EaipFetchError, match="effective date mismatch"):
            _validate_effective_date(f, CYCLE_2602.effective_date)

    def test_missing_meta_raises(self, tmp_path):
        f = tmp_path / ENR32_NAME
        f.write_text("<html><head></head><body></body></html>", encoding="utf-8")
        with pytest.raises(EaipFetchError, match="missing"):
            _validate_effective_date(f, CYCLE_2602.effective_date)

    def test_malformed_date_raises(self, tmp_path):
        f = tmp_path / ENR32_NAME
        f.write_text(
            '<html><head>'
            '<meta name="EM.effectiveDateStart" content="not-a-date">'
            '</head></html>',
            encoding="utf-8",
        )
        with pytest.raises(EaipFetchError, match="could not parse"):
            _validate_effective_date(f, CYCLE_2602.effective_date)


# ---------------------------------------------------------------------------
# fetch_eaip_html — integration (fully mocked network)
# ---------------------------------------------------------------------------

class TestFetchEaipHtml:
    """End-to-end test of the public API with all network calls mocked."""

    def _make_realistic_zip(self, extra: dict | None = None) -> io.BytesIO:
        files = {name: _make_meta_html(CYCLE_2602.effective_date).encode() for name in ALL_REQUIRED}
        if extra:
            files.update(extra)
        return _make_zip(files)

    def _patch_fetch(self, page_html: str, zip_buf: io.BytesIO):
        """Return a context manager that patches _fetch_html and download_zip."""
        import unittest.mock as mock

        def fake_fetch_html(url, timeout=30):
            return page_html

        def fakedownload_zip(url, timeout=120):
            zip_buf.seek(0)
            return zip_buf

        return mock.patch.multiple(
            "src.sources.eaip_html",
            _fetch_html=fake_fetch_html,
            download_zip=fakedownload_zip,
        )

    def test_returns_all_required_files(self, tmp_path):
        zip_buf = self._make_realistic_zip()
        page = _make_index_html(CYCLE_2602, "https://example.com/aip.zip")
        with self._patch_fetch(page, zip_buf):
            result = fetch_eaip_html(CYCLE_2602, tmp_path, index_url=_BASE_URL)
        assert ALL_REQUIRED.issubset(set(result.keys()))

    def test_returns_ad2_files_when_present(self, tmp_path):
        zip_buf = self._make_realistic_zip(
            extra={EGEL_AD2_NAME: _make_meta_html(CYCLE_2602.effective_date).encode()}
        )
        page = _make_index_html(CYCLE_2602, "https://example.com/aip.zip")
        with self._patch_fetch(page, zip_buf):
            result = fetch_eaip_html(CYCLE_2602, tmp_path, index_url=_BASE_URL)
        assert EGEL_AD2_NAME in result
        assert result[EGEL_AD2_NAME].parent == tmp_path / "ad2"

    def test_no_ad2_files_warns_but_does_not_raise(self, tmp_path):
        zip_buf = self._make_realistic_zip()
        page = _make_index_html(CYCLE_2602, "https://example.com/aip.zip")
        with self._patch_fetch(page, zip_buf):
            result = fetch_eaip_html(CYCLE_2602, tmp_path, index_url=_BASE_URL)
        assert ALL_REQUIRED.issubset(set(result.keys()))

    def test_dest_dir_created_if_missing(self, tmp_path):
        target = tmp_path / "new" / "subdir"
        assert not target.exists()
        zip_buf = self._make_realistic_zip()
        page = _make_index_html(CYCLE_2602, "https://example.com/aip.zip")
        with self._patch_fetch(page, zip_buf):
            fetch_eaip_html(CYCLE_2602, target, index_url=_BASE_URL)
        assert target.is_dir()

    def test_files_written_to_dest_dir(self, tmp_path):
        zip_buf = self._make_realistic_zip()
        page = _make_index_html(CYCLE_2602, "https://example.com/aip.zip")
        with self._patch_fetch(page, zip_buf):
            result = fetch_eaip_html(CYCLE_2602, tmp_path, index_url=_BASE_URL)
        for path in result.values():
            assert path.exists()
            assert path.parent == tmp_path

    def test_validate_false_skips_meta_check(self, tmp_path):
        """With validate=False files with no meta tag are accepted."""
        buf = _make_zip({name: b"<html/>" for name in ALL_REQUIRED})
        page = _make_index_html(CYCLE_2602, "https://example.com/aip.zip")
        with self._patch_fetch(page, buf):
            result = fetch_eaip_html(CYCLE_2602, tmp_path, index_url=_BASE_URL, validate=False)
        assert ALL_REQUIRED.issubset(set(result.keys()))

    def test_validate_true_raises_on_date_mismatch(self, tmp_path):
        wrong_date = date(2000, 1, 1)
        buf = _make_zip({name: _make_meta_html(wrong_date).encode() for name in ALL_REQUIRED})
        page = _make_index_html(CYCLE_2602, "https://example.com/aip.zip")
        with self._patch_fetch(page, buf):
            with pytest.raises(EaipFetchError, match="effective date mismatch"):
                fetch_eaip_html(CYCLE_2602, tmp_path, index_url=_BASE_URL, validate=True)

    def test_heading_missing_raises(self, tmp_path):
        page = "<html><body><h3>AIRAC 99/1999</h3></body></html>"
        zip_buf = self._make_realistic_zip()
        with self._patch_fetch(page, zip_buf):
            with pytest.raises(EaipFetchError, match="AIRAC 02/2026"):
                fetch_eaip_html(CYCLE_2602, tmp_path, index_url=_BASE_URL)
