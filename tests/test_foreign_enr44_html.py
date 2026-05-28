"""Tests for non-UK ENR 4.4 HTML support-file fetches."""

from __future__ import annotations

import urllib.error
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src.airac import cycle_for_date
from src.sources.foreign_enr44_html import (
    FRENCH_ENR44_HTML_FILENAME,
    IRISH_ENR44_HTML_FILENAME,
    _french_enr44_url,
    _irish_enr44_url,
    fetch_french_enr44_html,
    fetch_irish_enr44_html,
)

CYCLE_2603 = cycle_for_date(date(2026, 3, 19))


def test_irish_enr44_url_uses_cycle_effective_date():
    assert _irish_enr44_url(CYCLE_2603, "https://www.airnav.ie/AIRAC") == (
        "https://www.airnav.ie/AIRAC/2026-03-19-AIRAC/html/eAIP/"
        "EI-ENR-4.4-en-IE.html"
    )


def test_french_enr44_url_uses_sia_dvd_cycle_path():
    assert _french_enr44_url(
        CYCLE_2603,
        "https://www.sia.aviation-civile.gouv.fr/media/dvd",
    ) == (
        "https://www.sia.aviation-civile.gouv.fr/media/dvd/eAIP_19_MAR_2026"
        "/FRANCE/AIRAC-2026-03-19/html/eAIP/FR-ENR-4.4-fr-FR.html"
    )


def test_fetch_irish_enr44_html_writes_expected_file(tmp_path):
    def fake_download(url: str, dest: Path, timeout: int = 60) -> None:
        dest.write_text(f"<html>{url}</html>", encoding="utf-8")

    with patch("src.sources.foreign_enr44_html._download_html", side_effect=fake_download):
        result = fetch_irish_enr44_html(
            CYCLE_2603,
            tmp_path,
            base_url="https://irish.example/AIRAC",
        )

    assert result == tmp_path / IRISH_ENR44_HTML_FILENAME
    assert "https://irish.example/AIRAC/2026-03-19-AIRAC" in result.read_text(encoding="utf-8")


def test_fetch_french_enr44_html_writes_expected_file(tmp_path):
    def fake_download(url: str, dest: Path, timeout: int = 60) -> None:
        dest.write_text(f"<html>{url}</html>", encoding="utf-8")

    with patch("src.sources.foreign_enr44_html._download_html", side_effect=fake_download):
        result = fetch_french_enr44_html(
            CYCLE_2603,
            tmp_path,
            base_url="https://french.example/media/dvd",
        )

    assert result == tmp_path / FRENCH_ENR44_HTML_FILENAME
    assert "https://french.example/media/dvd/eAIP_19_MAR_2026" in result.read_text(encoding="utf-8")


def test_fetch_irish_enr44_html_returns_none_on_http_error(tmp_path):
    err = urllib.error.HTTPError("https://example.test", 404, "not found", hdrs=None, fp=None)

    with patch("src.sources.foreign_enr44_html._download_html", side_effect=err):
        result = fetch_irish_enr44_html(CYCLE_2603, tmp_path)

    assert result is None
    assert not (tmp_path / IRISH_ENR44_HTML_FILENAME).exists()


def test_fetch_french_enr44_html_returns_none_on_url_error(tmp_path):
    err = urllib.error.URLError("connection refused")

    with patch("src.sources.foreign_enr44_html._download_html", side_effect=err):
        result = fetch_french_enr44_html(CYCLE_2603, tmp_path)

    assert result is None
    assert not (tmp_path / FRENCH_ENR44_HTML_FILENAME).exists()


def test_fetch_french_enr44_html_returns_none_on_io_error(tmp_path):
    with patch("src.sources.foreign_enr44_html._download_html", side_effect=OSError("disk full")):
        result = fetch_french_enr44_html(CYCLE_2603, tmp_path)

    assert result is None
    assert not (tmp_path / FRENCH_ENR44_HTML_FILENAME).exists()
