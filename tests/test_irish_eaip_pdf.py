"""Unit tests for src/sources/irish_eaip_pdf.py.

All tests are offline: HTTP is replaced via unittest.mock.patch.
All filesystem writes go through pytest's tmp_path fixture.
"""

from __future__ import annotations

import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.sources.irish_eaip_pdf import (
    IrishEaipFetchError,
    PDF_FILENAME,
    _BASE_URL,
    _IAIP_PACKAGE_URL,
    _find_enr44_url,
    _fetch_page,
    fetch_irish_enr44,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

FAKE_GUID = "e3c9008c-779a-425f-84c4-a88425528047"
FAKE_PDF_URL = f"{_BASE_URL}/getattachment/{FAKE_GUID}/EI_ENR_4_4_EN.pdf?lang=en-IE"
FAKE_PDF_BYTES = b"%PDF-1.4 fake Irish ENR 4.4 content"


def _make_iaip_page(guid: str = FAKE_GUID) -> str:
    """Return minimal IAIP package HTML containing an ENR 4.4 link."""
    return (
        "<html><body>"
        f'<a href="/getattachment/{guid}/EI_ENR_4_4_EN.pdf?lang=en-IE">ENR 4.4</a>'
        "</body></html>"
    )


def _patch_fetch_page(html: str):
    """Patch _fetch_page to return *html*."""
    return patch("src.sources.irish_eaip_pdf._fetch_page", return_value=html)


def _patch_download_pdf(content: bytes = FAKE_PDF_BYTES):
    """Patch _download_pdf to write *content* to the dest path."""
    def fake_download(url, dest, timeout=60):
        dest.write_bytes(content)
    return patch("src.sources.irish_eaip_pdf._download_pdf", side_effect=fake_download)


# ---------------------------------------------------------------------------
# _find_enr44_url
# ---------------------------------------------------------------------------

class TestFindEnr44Url:
    def test_finds_link_in_realistic_html(self):
        html = _make_iaip_page(FAKE_GUID)
        url, guid = _find_enr44_url(html)
        assert guid == FAKE_GUID
        assert f"getattachment/{FAKE_GUID}/EI_ENR_4_4_EN.pdf" in url

    def test_url_is_absolute(self):
        html = _make_iaip_page(FAKE_GUID)
        url, _ = _find_enr44_url(html)
        assert url.startswith("https://")

    def test_custom_base_url(self):
        html = _make_iaip_page(FAKE_GUID)
        url, _ = _find_enr44_url(html, base_url="https://example.com")
        assert url.startswith("https://example.com")

    def test_different_guid_extracted(self):
        other_guid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        html = _make_iaip_page(other_guid)
        _, guid = _find_enr44_url(html)
        assert guid == other_guid

    def test_link_not_found_raises(self):
        html = "<html><body><p>No ENR 4.4 here</p></body></html>"
        with pytest.raises(IrishEaipFetchError, match="Could not find"):
            _find_enr44_url(html)

    def test_similar_enr_links_not_confused(self):
        """ENR 4.1, 4.3, 4.5 must not match the ENR 4.4 regex."""
        html = (
            "<html><body>"
            f'<a href="/getattachment/aaa/EI_ENR_4_1_EN.pdf">ENR 4.1</a>'
            f'<a href="/getattachment/bbb/EI_ENR_4_3_EN.pdf">ENR 4.3</a>'
            f'<a href="/getattachment/ccc/EI_ENR_4_5_EN.pdf">ENR 4.5</a>'
            "</body></html>"
        )
        with pytest.raises(IrishEaipFetchError):
            _find_enr44_url(html)

    def test_first_match_used_when_multiple(self):
        """If the page somehow contains two ENR 4.4 links, the first is used."""
        html = (
            "<html><body>"
            f'<a href="/getattachment/first-guid-aaa/EI_ENR_4_4_EN.pdf">ENR 4.4</a>'
            f'<a href="/getattachment/second-guid-bbb/EI_ENR_4_4_EN.pdf">ENR 4.4 (2)</a>'
            "</body></html>"
        )
        _, guid = _find_enr44_url(html)
        assert guid == "first-guid-aaa"


# ---------------------------------------------------------------------------
# fetch_irish_enr44 — success paths
# ---------------------------------------------------------------------------

class TestFetchIrishEnr44Success:
    def test_returns_path_on_success(self, tmp_path):
        html = _make_iaip_page()
        with _patch_fetch_page(html), _patch_download_pdf():
            result = fetch_irish_enr44(tmp_path)
        assert result is not None
        assert result.name == PDF_FILENAME

    def test_file_written_to_dest_dir(self, tmp_path):
        html = _make_iaip_page()
        with _patch_fetch_page(html), _patch_download_pdf():
            result = fetch_irish_enr44(tmp_path)
        assert result is not None
        assert result.parent == tmp_path
        assert result.exists()

    def test_dest_dir_created_if_missing(self, tmp_path):
        target = tmp_path / "new" / "subdir"
        assert not target.exists()
        html = _make_iaip_page()
        with _patch_fetch_page(html), _patch_download_pdf():
            fetch_irish_enr44(target)
        assert target.is_dir()

    def test_custom_page_url_passed_through(self, tmp_path):
        """page_url kwarg should be forwarded to _fetch_page."""
        captured = []
        def fake_fetch(url, timeout=30):
            captured.append(url)
            return _make_iaip_page()
        with patch("src.sources.irish_eaip_pdf._fetch_page", side_effect=fake_fetch):
            with _patch_download_pdf():
                fetch_irish_enr44(tmp_path, page_url="https://custom.example.com/page")
        assert captured == ["https://custom.example.com/page"]

    def test_default_page_url_is_airnav(self, tmp_path):
        captured = []
        def fake_fetch(url, timeout=30):
            captured.append(url)
            return _make_iaip_page()
        with patch("src.sources.irish_eaip_pdf._fetch_page", side_effect=fake_fetch):
            with _patch_download_pdf():
                fetch_irish_enr44(tmp_path)
        assert captured[0] == _IAIP_PACKAGE_URL


# ---------------------------------------------------------------------------
# fetch_irish_enr44 — non-fatal failure paths (returns None, no raise)
# ---------------------------------------------------------------------------

class TestFetchIrishEnr44NonFatal:
    def test_http_error_on_page_returns_none(self, tmp_path):
        err = urllib.error.HTTPError("url", 503, "Service Unavailable", {}, None)
        with patch("src.sources.irish_eaip_pdf._fetch_page", side_effect=err):
            result = fetch_irish_enr44(tmp_path)
        assert result is None

    def test_network_error_on_page_returns_none(self, tmp_path):
        err = urllib.error.URLError("connection refused")
        with patch("src.sources.irish_eaip_pdf._fetch_page", side_effect=err):
            result = fetch_irish_enr44(tmp_path)
        assert result is None

    def test_link_not_found_returns_none(self, tmp_path):
        with _patch_fetch_page("<html><p>no link</p></html>"):
            result = fetch_irish_enr44(tmp_path)
        assert result is None

    def test_http_error_on_pdf_download_returns_none(self, tmp_path):
        err = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
        html = _make_iaip_page()
        with _patch_fetch_page(html):
            with patch("src.sources.irish_eaip_pdf._download_pdf", side_effect=err):
                result = fetch_irish_enr44(tmp_path)
        assert result is None

    def test_network_error_on_pdf_download_returns_none(self, tmp_path):
        err = urllib.error.URLError("timeout")
        html = _make_iaip_page()
        with _patch_fetch_page(html):
            with patch("src.sources.irish_eaip_pdf._download_pdf", side_effect=err):
                result = fetch_irish_enr44(tmp_path)
        assert result is None

    def test_oserror_on_pdf_write_returns_none(self, tmp_path):
        html = _make_iaip_page()
        with _patch_fetch_page(html):
            with patch("src.sources.irish_eaip_pdf._download_pdf", side_effect=OSError("disk full")):
                result = fetch_irish_enr44(tmp_path)
        assert result is None

    def test_no_partial_file_left_on_page_failure(self, tmp_path):
        err = urllib.error.URLError("offline")
        with patch("src.sources.irish_eaip_pdf._fetch_page", side_effect=err):
            fetch_irish_enr44(tmp_path)
        assert not (tmp_path / PDF_FILENAME).exists()
