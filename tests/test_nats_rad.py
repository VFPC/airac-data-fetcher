"""Unit tests for src/sources/nats_rad.py.

All tests are offline: HTTP is replaced via unittest.mock.patch.
All filesystem writes go through pytest's tmp_path fixture.
"""

from __future__ import annotations

import urllib.error
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.airac import AiracCycle
from src.sources.nats_rad import (
    RadFetchError,
    _RAD_BASE_URL,
    _RAD_INDEX_URL,
    _find_workbook_url,
    fetch_rad,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CYCLE_2606 = AiracCycle(
    year=2026,
    number=6,
    effective_date=date(2026, 6, 11),
    expiry_date=date(2026, 7, 8),
)

CYCLE_2607 = AiracCycle(
    year=2026,
    number=7,
    effective_date=date(2026, 7, 9),
    expiry_date=date(2026, 8, 5),
)

# Minimal HTML reproducing the structure served by nm.eurocontrol.int/RAD/index.html
_INDEX_HTML_BOTH_CYCLES = """\
<html><body>
<a href="assets/AIRAC-RAD_DATA/CURRENT_AIRAC/RAD_2606_v1_12.xlsx">Latest Version</a>
<a href="assets/AIRAC-RAD_DATA/AIRAC+1/RAD_2607_v1_0.xlsx">Latest Version</a>
</body></html>
"""

_INDEX_HTML_2606_ONLY = """\
<html><body>
<a href="assets/AIRAC-RAD_DATA/CURRENT_AIRAC/RAD_2606_v1_12.xlsx">Latest Version</a>
</body></html>
"""

_INDEX_HTML_NO_MATCH = """\
<html><body>
<a href="assets/AIRAC-RAD_DATA/CURRENT_AIRAC/RAD_2605_v1_16.xlsx">Latest Version</a>
</body></html>
"""

_INDEX_HTML_MULTIPLE_VERSIONS = """\
<html><body>
<a href="assets/AIRAC-RAD_DATA/PREVIOUS/RAD_2606_v1_10.xlsx">Previous</a>
<a href="assets/AIRAC-RAD_DATA/CURRENT_AIRAC/RAD_2606_v1_12.xlsx">Latest Version</a>
</body></html>
"""

# Same cycle appears in both CURRENT_AIRAC and AIRAC+1 buckets during a transition
_INDEX_HTML_SAME_CYCLE_TWO_BUCKETS = """\
<html><body>
<a href="assets/AIRAC-RAD_DATA/CURRENT_AIRAC/RAD_2606_v1_10.xlsx">Latest Version</a>
<a href="assets/AIRAC-RAD_DATA/AIRAC+1/RAD_2606_v1_12.xlsx">Latest Version</a>
</body></html>
"""


# ---------------------------------------------------------------------------
# Tests for _find_workbook_url
# ---------------------------------------------------------------------------

class TestFindWorkbookUrl:
    def test_finds_current_cycle(self):
        url = _find_workbook_url(_INDEX_HTML_2606_ONLY, CYCLE_2606, _RAD_BASE_URL)
        assert url == _RAD_BASE_URL + "assets/AIRAC-RAD_DATA/CURRENT_AIRAC/RAD_2606_v1_12.xlsx"

    def test_finds_cycle_among_two(self):
        url = _find_workbook_url(_INDEX_HTML_BOTH_CYCLES, CYCLE_2606, _RAD_BASE_URL)
        assert "RAD_2606" in url
        assert "RAD_2607" not in url

    def test_finds_next_cycle(self):
        url = _find_workbook_url(_INDEX_HTML_BOTH_CYCLES, CYCLE_2607, _RAD_BASE_URL)
        assert "RAD_2607" in url

    def test_picks_highest_version_when_multiple(self):
        url = _find_workbook_url(_INDEX_HTML_MULTIPLE_VERSIONS, CYCLE_2606, _RAD_BASE_URL)
        assert "v1_12" in url

    def test_raises_when_no_match(self):
        with pytest.raises(RadFetchError, match="No RAD workbook found"):
            _find_workbook_url(_INDEX_HTML_NO_MATCH, CYCLE_2606, _RAD_BASE_URL)

    def test_resolves_relative_url_against_base(self):
        url = _find_workbook_url(_INDEX_HTML_2606_ONLY, CYCLE_2606, _RAD_BASE_URL)
        assert url.startswith("https://")

    def test_same_cycle_in_two_buckets_picks_highest_version(self):
        """When the same cycle appears in CURRENT_AIRAC and AIRAC+1 (transition period),
        the highest version number wins regardless of bucket.  This is the documented
        tie-break policy: version quality, not bucket position."""
        url = _find_workbook_url(
            _INDEX_HTML_SAME_CYCLE_TWO_BUCKETS, CYCLE_2606, _RAD_BASE_URL
        )
        assert "v1_12" in url
        assert "AIRAC+1" in url  # the higher version happened to be in AIRAC+1 here

    def test_handles_absolute_href(self):
        html = (
            '<html><body>'
            '<a href="https://www.nm.eurocontrol.int/RAD/assets/AIRAC-RAD_DATA/'
            'CURRENT_AIRAC/RAD_2606_v1_12.xlsx">Latest</a>'
            '</body></html>'
        )
        url = _find_workbook_url(html, CYCLE_2606, _RAD_BASE_URL)
        assert url == (
            "https://www.nm.eurocontrol.int/RAD/assets/AIRAC-RAD_DATA/"
            "CURRENT_AIRAC/RAD_2606_v1_12.xlsx"
        )


# ---------------------------------------------------------------------------
# Tests for fetch_rad (integration, HTTP mocked)
# ---------------------------------------------------------------------------

def _make_fake_urlopen(index_html: str, workbook_bytes: bytes):
    """Return a context-manager factory that serves index_html then workbook_bytes."""
    call_count = {"n": 0}

    class FakeResp:
        def __init__(self, data: bytes):
            self._data = data

        def read(self):
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return FakeResp(index_html.encode("utf-8"))
        return FakeResp(workbook_bytes)

    return fake_urlopen


class TestFetchRad:
    def test_downloads_workbook_to_dest_dir(self, tmp_path):
        fake_bytes = b"PK\x03\x04fake xlsx content"
        urlopen = _make_fake_urlopen(_INDEX_HTML_2606_ONLY, fake_bytes)

        with patch("src.sources.nats_rad.urllib.request.urlopen", side_effect=urlopen):
            path = fetch_rad(CYCLE_2606, tmp_path)

        assert path.name == "RAD_2606_v1_12.xlsx"
        assert path.parent == tmp_path
        assert path.read_bytes() == fake_bytes

    def test_creates_dest_dir_if_absent(self, tmp_path):
        new_dir = tmp_path / "cycle" / "2606"
        fake_bytes = b"fake"
        urlopen = _make_fake_urlopen(_INDEX_HTML_2606_ONLY, fake_bytes)

        with patch("src.sources.nats_rad.urllib.request.urlopen", side_effect=urlopen):
            fetch_rad(CYCLE_2606, new_dir)

        assert new_dir.is_dir()

    def test_raises_on_index_http_error(self, tmp_path):
        def fail_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                _RAD_INDEX_URL, 503, "Service Unavailable", {}, None
            )

        with patch("src.sources.nats_rad.urllib.request.urlopen", side_effect=fail_urlopen):
            with pytest.raises(RadFetchError, match="HTTP 503"):
                fetch_rad(CYCLE_2606, tmp_path)

    def test_raises_on_download_http_error(self, tmp_path):
        call_count = {"n": 0}

        def partial_urlopen(req, timeout=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                class FakeIndex:
                    def read(self): return _INDEX_HTML_2606_ONLY.encode()
                    def __enter__(self): return self
                    def __exit__(self, *a): pass
                return FakeIndex()
            raise urllib.error.HTTPError(
                "https://example.com/RAD_2606_v1_12.xlsx",
                403, "Forbidden", {}, None,
            )

        with patch("src.sources.nats_rad.urllib.request.urlopen", side_effect=partial_urlopen):
            with pytest.raises(RadFetchError, match="HTTP 403"):
                fetch_rad(CYCLE_2606, tmp_path)

    def test_raises_when_cycle_not_on_page(self, tmp_path):
        urlopen = _make_fake_urlopen(_INDEX_HTML_NO_MATCH, b"")

        with patch("src.sources.nats_rad.urllib.request.urlopen", side_effect=urlopen):
            with pytest.raises(RadFetchError, match="No RAD workbook found"):
                fetch_rad(CYCLE_2606, tmp_path)

    def test_no_temp_files_left_on_success(self, tmp_path):
        fake_bytes = b"fake xlsx"
        urlopen = _make_fake_urlopen(_INDEX_HTML_2606_ONLY, fake_bytes)

        with patch("src.sources.nats_rad.urllib.request.urlopen", side_effect=urlopen):
            fetch_rad(CYCLE_2606, tmp_path)

        leftover = [p for p in tmp_path.iterdir() if p.name.startswith(".rad_tmp_")]
        assert not leftover, f"Temp dir not cleaned up: {leftover}"

    def test_custom_index_url_is_used(self, tmp_path):
        custom_url = "https://example.com/RAD/index.html"
        seen_urls = []

        def recording_urlopen(req, timeout=None):
            seen_urls.append(req.full_url)
            if len(seen_urls) == 1:
                class FakeIndex:
                    def read(self): return _INDEX_HTML_2606_ONLY.encode()
                    def __enter__(self): return self
                    def __exit__(self, *a): pass
                return FakeIndex()
            class FakeWork:
                def read(self): return b"fake"
                def __enter__(self): return self
                def __exit__(self, *a): pass
            return FakeWork()

        with patch("src.sources.nats_rad.urllib.request.urlopen", side_effect=recording_urlopen):
            fetch_rad(CYCLE_2606, tmp_path, index_url=custom_url)

        assert seen_urls[0] == custom_url
