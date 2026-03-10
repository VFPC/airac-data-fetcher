"""Unit tests for src/sources/nats_srd.py.

All tests are offline: HTTP is replaced via unittest.mock.patch.
All filesystem writes go through pytest's tmp_path fixture.
"""

from __future__ import annotations

import io
import urllib.error
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.airac import AiracCycle
from src.sources.nats_srd import (
    SrdFetchError,
    _SRD_BASE,
    _extract_excel,
    _srd_zip_url,
    fetch_srd,
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

CYCLE_2603 = AiracCycle(
    year=2026,
    number=3,
    effective_date=date(2026, 3, 19),
    expiry_date=date(2026, 4, 15),
)

CYCLE_2601 = AiracCycle(
    year=2026,
    number=1,
    effective_date=date(2026, 1, 22),
    expiry_date=date(2026, 2, 18),
)

SRD_XLSX_NAME = "UK_ENR_Standard_Routes_2602.xlsx"
SRD_XLS_NAME = "UK_ENR_Standard_Routes_2602.xls"


def _make_zip(files: dict[str, bytes]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    buf.seek(0)
    return buf


def _patch_download(zip_buf: io.BytesIO):
    """Patch _download_zip to return *zip_buf* (seeked to 0 each call)."""
    def fake_download(url, timeout=120):
        zip_buf.seek(0)
        return zip_buf
    return patch("src.sources.nats_srd._download_zip", side_effect=fake_download)


# ---------------------------------------------------------------------------
# _srd_zip_url
# ---------------------------------------------------------------------------

class TestSrdZipUrl:
    def test_url_for_2602(self):
        # [RULE:SRD-DOWNLOAD-URL]
        url = _srd_zip_url(CYCLE_2602)
        assert url == f"{_SRD_BASE}AIRAC-02-2026.zip"

    def test_url_for_2603(self):
        # [RULE:SRD-DOWNLOAD-URL]
        url = _srd_zip_url(CYCLE_2603)
        assert url == f"{_SRD_BASE}AIRAC-03-2026.zip"

    def test_cycle_number_zero_padded(self):
        # [RULE:SRD-DOWNLOAD-URL] single-digit cycle numbers must be padded to 2 digits
        url = _srd_zip_url(CYCLE_2601)
        assert "AIRAC-01-2026" in url

    def test_url_starts_with_base(self):
        url = _srd_zip_url(CYCLE_2602)
        assert url.startswith(_SRD_BASE)

    def test_url_ends_with_zip(self):
        url = _srd_zip_url(CYCLE_2602)
        assert url.endswith(".zip")

    def test_different_year(self):
        c = AiracCycle(year=2025, number=13, effective_date=date(2025, 12, 25), expiry_date=date(2026, 1, 21))
        url = _srd_zip_url(c)
        assert url == f"{_SRD_BASE}AIRAC-13-2025.zip"


# ---------------------------------------------------------------------------
# _extract_excel
# ---------------------------------------------------------------------------

class TestExtractExcel:
    def test_extracts_xlsx(self, tmp_path):
        content = b"fake xlsx content"
        buf = _make_zip({SRD_XLSX_NAME: content})
        result = _extract_excel(buf, tmp_path)
        assert SRD_XLSX_NAME in result
        assert result[SRD_XLSX_NAME].read_bytes() == content

    def test_extracts_xls(self, tmp_path):
        content = b"fake xls content"
        buf = _make_zip({SRD_XLS_NAME: content})
        result = _extract_excel(buf, tmp_path)
        assert SRD_XLS_NAME in result

    def test_files_written_to_dest_dir(self, tmp_path):
        buf = _make_zip({SRD_XLSX_NAME: b"data"})
        result = _extract_excel(buf, tmp_path)
        for path in result.values():
            assert path.parent == tmp_path

    def test_located_by_basename_in_nested_path(self, tmp_path):
        buf = _make_zip({f"subdir/nested/{SRD_XLSX_NAME}": b"data"})
        result = _extract_excel(buf, tmp_path)
        assert SRD_XLSX_NAME in result
        assert result[SRD_XLSX_NAME].exists()

    def test_multiple_excel_files_all_extracted(self, tmp_path):
        buf = _make_zip({SRD_XLSX_NAME: b"a", SRD_XLS_NAME: b"b"})
        result = _extract_excel(buf, tmp_path)
        assert set(result.keys()) == {SRD_XLSX_NAME, SRD_XLS_NAME}

    def test_non_excel_files_ignored(self, tmp_path):
        buf = _make_zip({
            SRD_XLSX_NAME: b"data",
            "README.txt": b"ignore",
            "manifest.xml": b"ignore",
        })
        result = _extract_excel(buf, tmp_path)
        assert set(result.keys()) == {SRD_XLSX_NAME}
        assert not (tmp_path / "README.txt").exists()

    def test_no_excel_raises(self, tmp_path):
        buf = _make_zip({"notes.txt": b"nothing useful"})
        with pytest.raises(SrdFetchError, match="no Excel files"):
            _extract_excel(buf, tmp_path)

    def test_empty_zip_raises(self, tmp_path):
        buf = _make_zip({})
        with pytest.raises(SrdFetchError, match="no Excel files"):
            _extract_excel(buf, tmp_path)

    def test_extension_case_insensitive(self, tmp_path):
        buf = _make_zip({"SRD.XLSX": b"data"})
        result = _extract_excel(buf, tmp_path)
        assert "SRD.XLSX" in result


# ---------------------------------------------------------------------------
# fetch_srd — integration (mocked network)
# ---------------------------------------------------------------------------

class TestFetchSrd:
    def test_returns_excel_dict(self, tmp_path):
        buf = _make_zip({SRD_XLSX_NAME: b"xlsx data"})
        with _patch_download(buf):
            result = fetch_srd(CYCLE_2602, tmp_path)
        assert SRD_XLSX_NAME in result

    def test_dest_dir_created_if_missing(self, tmp_path):
        target = tmp_path / "new" / "subdir"
        assert not target.exists()
        buf = _make_zip({SRD_XLSX_NAME: b"data"})
        with _patch_download(buf):
            fetch_srd(CYCLE_2602, target)
        assert target.is_dir()

    def test_files_written_to_dest_dir(self, tmp_path):
        buf = _make_zip({SRD_XLSX_NAME: b"data"})
        with _patch_download(buf):
            result = fetch_srd(CYCLE_2602, tmp_path)
        for path in result.values():
            assert path.exists()
            assert path.parent == tmp_path

    def test_correct_url_constructed(self, tmp_path):
        """Verify the URL passed to _download_zip matches [RULE:SRD-DOWNLOAD-URL]."""
        buf = _make_zip({SRD_XLSX_NAME: b"data"})
        captured_urls = []

        def fake_download(url, timeout=120):
            captured_urls.append(url)
            buf.seek(0)
            return buf

        with patch("src.sources.nats_srd._download_zip", side_effect=fake_download):
            fetch_srd(CYCLE_2602, tmp_path)

        assert len(captured_urls) == 1
        # [RULE:SRD-DOWNLOAD-URL]
        assert captured_urls[0] == f"{_SRD_BASE}AIRAC-02-2026.zip"

    def test_http_404_raises_srd_fetch_error(self, tmp_path):
        http_error = urllib.error.HTTPError(
            url="https://example.com", code=404, msg="Not Found", hdrs=None, fp=None
        )
        with patch("src.sources.nats_srd._download_zip", side_effect=http_error):
            with pytest.raises(SrdFetchError, match="HTTP 404"):
                fetch_srd(CYCLE_2602, tmp_path)

    def test_network_error_raises_srd_fetch_error(self, tmp_path):
        url_error = urllib.error.URLError("connection refused")
        with patch("src.sources.nats_srd._download_zip", side_effect=url_error):
            with pytest.raises(SrdFetchError, match="Network error"):
                fetch_srd(CYCLE_2602, tmp_path)

    def test_empty_zip_raises_srd_fetch_error(self, tmp_path):
        buf = _make_zip({})
        with _patch_download(buf):
            with pytest.raises(SrdFetchError, match="no Excel files"):
                fetch_srd(CYCLE_2602, tmp_path)
