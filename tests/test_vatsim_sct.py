"""Unit tests for src/sources/vatsim_sct.py.

All tests are offline: the GitHub API and zip download are fully mocked.
All filesystem writes go through pytest's tmp_path fixture.
"""

from __future__ import annotations

import io
import urllib.error
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from src.airac import AiracCycle
from src.sources.vatsim_sct import (
    SctFetchError,
    _RELEASES_API,
    _SCT_DATA_DIR,
    _extract_sct,
    _latest_tag_for_cycle,
    _matches_cycle,
    _sct_basename,
    _source_zip_url,
    _tag_prefix,
    fetch_sct,
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

CYCLE_2601 = AiracCycle(
    year=2026,
    number=1,
    effective_date=date(2026, 1, 22),
    expiry_date=date(2026, 2, 18),
)

SCT_BASENAME_2602 = "UK_2026_02.sct"
SCT_CONTENT = b"; UK sector file content\n[INFO]\nUK_2026_02\n"


def _make_release(tag: str, published_at: str) -> dict:
    return {"tag_name": tag, "published_at": published_at}


def _make_zip_with_sct(
    sct_basename: str,
    content: bytes = SCT_CONTENT,
    zip_path: str | None = None,
) -> io.BytesIO:
    """Build an in-memory zip that contains the SCT file at the expected path."""
    if zip_path is None:
        zip_path = f"uk-controller-pack-2026_02a/{_SCT_DATA_DIR}{sct_basename}"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(zip_path, content)
    buf.seek(0)
    return buf


def _patch_api_and_zip(releases: list[dict], zip_buf: io.BytesIO):
    """Patch both _fetch_releases and download_zip."""
    def fake_fetch(url, timeout=30):
        return releases

    def fake_download(url, timeout=120):
        zip_buf.seek(0)
        return zip_buf

    return patch.multiple(
        "src.sources.vatsim_sct",
        _fetch_releases=fake_fetch,
        download_zip=fake_download,
    )


# ---------------------------------------------------------------------------
# _sct_basename / _tag_prefix
# ---------------------------------------------------------------------------

class TestNamingHelpers:
    def test_sct_basename_2602(self):
        # [RULE:SCT-FILE-PATH]
        assert _sct_basename(CYCLE_2602) == "UK_2026_02.sct"

    def test_sct_basename_zero_padded(self):
        # [RULE:SCT-FILE-PATH] single-digit cycle numbers must be padded
        assert _sct_basename(CYCLE_2601) == "UK_2026_01.sct"

    def test_sct_basename_cycle_13(self):
        c = AiracCycle(year=2025, number=13, effective_date=date(2025, 12, 25), expiry_date=date(2026, 1, 21))
        assert _sct_basename(c) == "UK_2025_13.sct"

    def test_tag_prefix_2602(self):
        # [RULE:SCT-RELEASE-TAG]
        assert _tag_prefix(CYCLE_2602) == "2026_02"

    def test_tag_prefix_zero_padded(self):
        # [RULE:SCT-RELEASE-TAG]
        assert _tag_prefix(CYCLE_2601) == "2026_01"


# ---------------------------------------------------------------------------
# _matches_cycle
# ---------------------------------------------------------------------------

class TestMatchesCycle:
    def test_base_tag_matches(self):
        # [RULE:SCT-RELEASE-TAG]
        assert _matches_cycle("2026_02", CYCLE_2602)

    def test_patch_a_matches(self):
        # [RULE:SCT-RELEASE-TAG]
        assert _matches_cycle("2026_02a", CYCLE_2602)

    def test_patch_b_matches(self):
        assert _matches_cycle("2026_02b", CYCLE_2602)

    def test_different_cycle_does_not_match(self):
        assert not _matches_cycle("2026_01", CYCLE_2602)

    def test_different_year_does_not_match(self):
        assert not _matches_cycle("2025_02", CYCLE_2602)

    def test_malformed_tag_does_not_match(self):
        assert not _matches_cycle("2026/02", CYCLE_2602)
        assert not _matches_cycle("", CYCLE_2602)
        assert not _matches_cycle("latest", CYCLE_2602)


# ---------------------------------------------------------------------------
# _latest_tag_for_cycle
# ---------------------------------------------------------------------------

class TestLatestTagForCycle:
    def test_returns_base_when_only_one(self):
        releases = [_make_release("2026_02", "2026-02-19T05:38:00Z")]
        assert _latest_tag_for_cycle(releases, CYCLE_2602) == "2026_02"

    def test_picks_patch_over_base(self):
        releases = [
            _make_release("2026_02", "2026-02-19T05:38:00Z"),
            _make_release("2026_02a", "2026-02-19T14:20:00Z"),
        ]
        # [RULE:SCT-RELEASE-TAG] patch must win
        assert _latest_tag_for_cycle(releases, CYCLE_2602) == "2026_02a"

    def test_picks_latest_of_multiple_patches(self):
        releases = [
            _make_release("2026_02a", "2026-02-19T14:20:00Z"),
            _make_release("2026_02b", "2026-02-20T09:00:00Z"),
            _make_release("2026_02", "2026-02-19T05:38:00Z"),
        ]
        assert _latest_tag_for_cycle(releases, CYCLE_2602) == "2026_02b"

    def test_ignores_other_cycles(self):
        releases = [
            _make_release("2026_01", "2026-01-22T04:23:00Z"),
            _make_release("2026_02", "2026-02-19T05:38:00Z"),
            _make_release("2026_03", "2026-03-19T00:00:00Z"),
        ]
        assert _latest_tag_for_cycle(releases, CYCLE_2602) == "2026_02"

    def test_no_matching_release_raises(self):
        releases = [_make_release("2026_01", "2026-01-22T04:23:00Z")]
        with pytest.raises(SctFetchError, match="2602"):
            _latest_tag_for_cycle(releases, CYCLE_2602)

    def test_empty_releases_raises(self):
        with pytest.raises(SctFetchError, match="2602"):
            _latest_tag_for_cycle([], CYCLE_2602)


# ---------------------------------------------------------------------------
# _source_zip_url
# ---------------------------------------------------------------------------

class TestSourceZipUrl:
    def test_contains_repo_and_tag(self):
        url = _source_zip_url("2026_02a")
        assert "VATSIM-UK/uk-controller-pack" in url
        assert "2026_02a" in url

    def test_ends_with_zip(self):
        assert _source_zip_url("2026_02a").endswith(".zip")

    def test_uses_refs_tags_path(self):
        url = _source_zip_url("2026_02a")
        assert "refs/tags" in url


# ---------------------------------------------------------------------------
# _extract_sct
# ---------------------------------------------------------------------------

class TestExtractSct:
    def test_extracts_file(self, tmp_path):
        buf = _make_zip_with_sct(SCT_BASENAME_2602)
        result = _extract_sct(buf, CYCLE_2602, tmp_path)
        assert result.exists()
        assert result.read_bytes() == SCT_CONTENT

    def test_returns_correct_path(self, tmp_path):
        buf = _make_zip_with_sct(SCT_BASENAME_2602)
        result = _extract_sct(buf, CYCLE_2602, tmp_path)
        assert result == tmp_path / SCT_BASENAME_2602

    def test_file_in_dest_dir(self, tmp_path):
        buf = _make_zip_with_sct(SCT_BASENAME_2602)
        result = _extract_sct(buf, CYCLE_2602, tmp_path)
        assert result.parent == tmp_path

    def test_tolerates_deep_nesting(self, tmp_path):
        """File can be nested arbitrarily deep inside the zip."""
        buf = _make_zip_with_sct(
            SCT_BASENAME_2602,
            zip_path=f"repo-root/some/prefix/{_SCT_DATA_DIR}{SCT_BASENAME_2602}",
        )
        result = _extract_sct(buf, CYCLE_2602, tmp_path)
        assert result.read_bytes() == SCT_CONTENT

    def test_wrong_basename_not_extracted(self, tmp_path):
        """A file in UK/data/ with a different name is not mistakenly extracted."""
        buf = _make_zip_with_sct(
            "UK_2026_01.sct",  # wrong cycle
            zip_path=f"repo/{_SCT_DATA_DIR}UK_2026_01.sct",
        )
        with pytest.raises(SctFetchError, match=SCT_BASENAME_2602):
            _extract_sct(buf, CYCLE_2602, tmp_path)

    def test_sct_not_in_data_dir_not_extracted(self, tmp_path):
        """An SCT file outside UK/data/ is not picked up."""
        buf = _make_zip_with_sct(
            SCT_BASENAME_2602,
            zip_path=f"repo/wrong_dir/{SCT_BASENAME_2602}",
        )
        with pytest.raises(SctFetchError, match=SCT_BASENAME_2602):
            _extract_sct(buf, CYCLE_2602, tmp_path)

    def test_missing_sct_raises(self, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("repo/README.md", "nothing")
        buf.seek(0)
        with pytest.raises(SctFetchError, match=SCT_BASENAME_2602):
            _extract_sct(buf, CYCLE_2602, tmp_path)

    def test_no_partial_files_on_missing_sct(self, tmp_path):
        """When the SCT file is not found, dest_dir must stay empty."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("repo/README.md", "nothing")
        buf.seek(0)
        with pytest.raises(SctFetchError):
            _extract_sct(buf, CYCLE_2602, tmp_path)
        assert list(tmp_path.iterdir()) == []

    def test_temp_dir_cleaned_up_on_success(self, tmp_path):
        buf = _make_zip_with_sct(SCT_BASENAME_2602)
        _extract_sct(buf, CYCLE_2602, tmp_path)
        remaining = [p for p in tmp_path.iterdir() if p.name.startswith(".sct_tmp_")]
        assert remaining == []

    def test_temp_dir_cleaned_up_on_failure(self, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("repo/README.md", "nothing")
        buf.seek(0)
        with pytest.raises(SctFetchError):
            _extract_sct(buf, CYCLE_2602, tmp_path)
        remaining = [p for p in tmp_path.iterdir() if p.name.startswith(".sct_tmp_")]
        assert remaining == []


# ---------------------------------------------------------------------------
# fetch_sct — integration (fully mocked)
# ---------------------------------------------------------------------------

class TestFetchSct:
    def _releases(self):
        return [
            _make_release("2026_02", "2026-02-19T05:38:00Z"),
            _make_release("2026_02a", "2026-02-19T14:20:00Z"),
        ]

    def test_returns_sct_path(self, tmp_path):
        releases = self._releases()
        zip_buf = _make_zip_with_sct(SCT_BASENAME_2602)
        with _patch_api_and_zip(releases, zip_buf):
            result = fetch_sct(CYCLE_2602, tmp_path)
        assert result == tmp_path / SCT_BASENAME_2602

    def test_file_written_to_dest_dir(self, tmp_path):
        zip_buf = _make_zip_with_sct(SCT_BASENAME_2602)
        with _patch_api_and_zip(self._releases(), zip_buf):
            result = fetch_sct(CYCLE_2602, tmp_path)
        assert result.exists()
        assert result.read_bytes() == SCT_CONTENT

    def test_dest_dir_created_if_missing(self, tmp_path):
        target = tmp_path / "new" / "subdir"
        assert not target.exists()
        zip_buf = _make_zip_with_sct(SCT_BASENAME_2602)
        with _patch_api_and_zip(self._releases(), zip_buf):
            fetch_sct(CYCLE_2602, target)
        assert target.is_dir()

    def test_latest_patch_tag_used(self, tmp_path):
        """Verify the patch tag (2026_02a) is preferred over the base (2026_02)."""
        captured_urls = []
        zip_buf = _make_zip_with_sct(SCT_BASENAME_2602)

        def fake_fetch(url, timeout=30):
            return self._releases()

        def fake_download(url, timeout=120):
            captured_urls.append(url)
            zip_buf.seek(0)
            return zip_buf

        with patch.multiple(
            "src.sources.vatsim_sct",
            _fetch_releases=fake_fetch,
            download_zip=fake_download,
        ):
            fetch_sct(CYCLE_2602, tmp_path)

        assert len(captured_urls) == 1
        # [RULE:SCT-RELEASE-TAG] patch 'a' must be preferred
        assert "2026_02a" in captured_urls[0]

    def test_no_matching_release_raises(self, tmp_path):
        with patch("src.sources.vatsim_sct._fetch_releases", return_value=[]):
            with pytest.raises(SctFetchError, match="2602"):
                fetch_sct(CYCLE_2602, tmp_path)

    def test_api_http_error_raises(self, tmp_path):
        http_err = urllib.error.HTTPError(
            url="https://api.github.com", code=403,
            msg="Forbidden", hdrs=None, fp=None,
        )
        with patch("src.sources.vatsim_sct._fetch_releases", side_effect=http_err):
            with pytest.raises(SctFetchError, match="HTTP 403"):
                fetch_sct(CYCLE_2602, tmp_path)

    def test_zip_http_error_raises(self, tmp_path):
        http_err = urllib.error.HTTPError(
            url="https://github.com", code=404,
            msg="Not Found", hdrs=None, fp=None,
        )

        def fake_fetch(url, timeout=30):
            return self._releases()

        with patch("src.sources.vatsim_sct._fetch_releases", side_effect=fake_fetch):
            with patch("src.sources.vatsim_sct.download_zip", side_effect=http_err):
                with pytest.raises(SctFetchError, match="HTTP 404"):
                    fetch_sct(CYCLE_2602, tmp_path)

    def test_custom_releases_api_url_passed_through(self, tmp_path):
        custom_url = "https://example.com/releases"
        captured = []
        zip_buf = _make_zip_with_sct(SCT_BASENAME_2602)

        def fake_fetch(url, timeout=30):
            captured.append(url)
            return self._releases()

        def fake_download(url, timeout=120):
            zip_buf.seek(0)
            return zip_buf

        with patch.multiple(
            "src.sources.vatsim_sct",
            _fetch_releases=fake_fetch,
            download_zip=fake_download,
        ):
            fetch_sct(CYCLE_2602, tmp_path, releases_api_url=custom_url)

        assert captured[0] == custom_url
