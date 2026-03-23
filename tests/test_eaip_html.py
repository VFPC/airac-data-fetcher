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
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from src.airac import AiracCycle
from src.sources.eaip_html import (
    EaipFetchError,
    _cycle_heading_text,
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

class TestExtractTargets:
    def test_extracts_both_files(self, tmp_path):
        content32 = b"<html>enr32</html>"
        content33 = b"<html>enr33</html>"
        buf = _make_zip({ENR32_NAME: content32, ENR33_NAME: content33})
        result = _extract_targets(buf, tmp_path)
        assert set(result.keys()) == {ENR32_NAME, ENR33_NAME}
        assert result[ENR32_NAME].read_bytes() == content32
        assert result[ENR33_NAME].read_bytes() == content33

    def test_files_extracted_into_dest_dir(self, tmp_path):
        buf = _make_zip({ENR32_NAME: b"a", ENR33_NAME: b"b"})
        result = _extract_targets(buf, tmp_path)
        for path in result.values():
            assert path.parent == tmp_path

    def test_located_by_basename_in_nested_path(self, tmp_path):
        """Files nested inside zip subdirectories are still found."""
        buf = _make_zip({
            f"deep/nested/path/{ENR32_NAME}": b"32",
            f"another/level/{ENR33_NAME}": b"33",
        })
        result = _extract_targets(buf, tmp_path)
        assert set(result.keys()) == {ENR32_NAME, ENR33_NAME}

    def test_missing_file_raises(self, tmp_path):
        buf = _make_zip({ENR32_NAME: b"only one"})
        with pytest.raises(EaipFetchError, match=ENR33_NAME):
            _extract_targets(buf, tmp_path)

    def test_both_missing_raises(self, tmp_path):
        buf = _make_zip({"unrelated.html": b"nothing"})
        with pytest.raises(EaipFetchError, match="missing expected files"):
            _extract_targets(buf, tmp_path)

    def test_extra_files_in_zip_are_ignored(self, tmp_path):
        buf = _make_zip({
            ENR32_NAME: b"32",
            ENR33_NAME: b"33",
            "EG-ENR-2.1-en-GB.html": b"ignore me",
        })
        result = _extract_targets(buf, tmp_path)
        assert set(result.keys()) == {ENR32_NAME, ENR33_NAME}
        assert not (tmp_path / "EG-ENR-2.1-en-GB.html").exists()

    def test_no_partial_files_on_missing_target(self, tmp_path):
        """When one target is missing, the other must NOT be left in dest_dir."""
        buf = _make_zip({ENR32_NAME: b"only one"})
        with pytest.raises(EaipFetchError):
            _extract_targets(buf, tmp_path)
        assert not (tmp_path / ENR32_NAME).exists()

    def test_temp_dir_cleaned_up_on_success(self, tmp_path):
        buf = _make_zip({ENR32_NAME: b"32", ENR33_NAME: b"33"})
        _extract_targets(buf, tmp_path)
        remaining = [p for p in tmp_path.iterdir() if p.name.startswith(".eaip_tmp_")]
        assert remaining == []

    def test_temp_dir_cleaned_up_on_failure(self, tmp_path):
        buf = _make_zip({"unrelated.html": b"nothing"})
        with pytest.raises(EaipFetchError):
            _extract_targets(buf, tmp_path)
        remaining = [p for p in tmp_path.iterdir() if p.name.startswith(".eaip_tmp_")]
        assert remaining == []


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

    def _make_realistic_zip(self) -> io.BytesIO:
        return _make_zip({
            ENR32_NAME: _make_meta_html(CYCLE_2602.effective_date).encode(),
            ENR33_NAME: _make_meta_html(CYCLE_2602.effective_date).encode(),
        })

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

    def test_returns_both_files(self, tmp_path):
        zip_buf = self._make_realistic_zip()
        page = _make_index_html(CYCLE_2602, "https://example.com/aip.zip")
        with self._patch_fetch(page, zip_buf):
            result = fetch_eaip_html(CYCLE_2602, tmp_path, index_url=_BASE_URL)
        assert set(result.keys()) == {ENR32_NAME, ENR33_NAME}

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
        """With validate=False a file with no meta tag is accepted."""
        buf = _make_zip({ENR32_NAME: b"<html/>", ENR33_NAME: b"<html/>"})
        page = _make_index_html(CYCLE_2602, "https://example.com/aip.zip")
        with self._patch_fetch(page, buf):
            result = fetch_eaip_html(CYCLE_2602, tmp_path, index_url=_BASE_URL, validate=False)
        assert set(result.keys()) == {ENR32_NAME, ENR33_NAME}

    def test_validate_true_raises_on_date_mismatch(self, tmp_path):
        wrong_date = date(2000, 1, 1)
        buf = _make_zip({
            ENR32_NAME: _make_meta_html(wrong_date).encode(),
            ENR33_NAME: _make_meta_html(wrong_date).encode(),
        })
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
