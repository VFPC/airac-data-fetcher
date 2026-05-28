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
    Enr44HtmlLinkNotFound,
    _find_french_product_enr44_url,
    _find_irish_eaip_enr44_url,
    _french_enr44_url,
    _irish_enr44_url,
    fetch_french_enr44_html,
    fetch_irish_enr44_html,
)

CYCLE_2603 = cycle_for_date(date(2026, 3, 19))
CYCLE_2606 = cycle_for_date(date(2026, 6, 11))


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


def test_irish_portal_discovery_uses_matching_effective_date():
    html = """
    <h2>AIRAC AMDT 002/2026 ; EFF 19 FEB 2026</h2>
    <h3><a href="2026-02-19-AIRAC/html/index.html">eAIP</a></h3>
    <h2>FUTURE AIRAC AMDT 003/2026 ; EFF 19 MAR 2026</h2>
    <h3><a href="2026-03-19-AIRAC/html/index.html">eAIP</a></h3>
    """

    assert _find_irish_eaip_enr44_url(html, CYCLE_2603, "https://www.airnav.ie/AIRAC/index.html") == (
        "https://www.airnav.ie/AIRAC/2026-03-19-AIRAC/html/eAIP/EI-ENR-4.4-en-IE.html"
    )


def test_irish_portal_discovery_returns_unavailable_for_tba_future_cycle():
    html = """
    <h2>AIRAC AMDT 005/2026 ; EFF 14 MAY 2026</h2>
    <h3><a href="2026-05-14-AIRAC/html/index.html">eAIP</a></h3>
    <h2>FUTURE AIRAC AMDT 006/2026 ; EFF 11 JUN 2026</h2>
    <h3>TBA</h3>
    """

    try:
        _find_irish_eaip_enr44_url(html, CYCLE_2606, "https://www.airnav.ie/AIRAC/index.html")
    except Enr44HtmlLinkNotFound:
        pass
    else:
        raise AssertionError("future TBA cycle should not resolve to the current eAIP")


def test_irish_portal_discovery_stops_at_next_h3_cycle_heading():
    html = """
    <h3>FUTURE AIRAC AMDT 006/2026 ; EFF 11 JUN 2026</h3>
    <p>TBA</p>
    <h3>AIRAC AMDT 007/2026 ; EFF 09 JUL 2026</h3>
    <h4><a href="2026-07-09-AIRAC/html/index.html">eAIP</a></h4>
    """

    try:
        _find_irish_eaip_enr44_url(html, CYCLE_2606, "https://www.airnav.ie/AIRAC/index.html")
    except Enr44HtmlLinkNotFound:
        pass
    else:
        raise AssertionError("target TBA h3 cycle should not scan into the next h3 cycle block")


def test_french_products_discovery_requires_matching_airac_product():
    html = """
    <ol>
      <li>
        <a href="/zip-eaip-complet-airac-02-26.html">ZIP eAIP Complet AIRAC 02/26</a>
        En vigueur du 19/02/2026 au 18/03/2026 inclus
      </li>
      <li>
        <a href="/zip-eaip-complet-airac-03-26.html">ZIP eAIP Complet AIRAC 03/26</a>
        En vigueur du 19/03/2026 au 15/04/2026 inclus
      </li>
    </ol>
    """

    assert _find_french_product_enr44_url(
        html,
        CYCLE_2603,
        base_url="https://www.sia.aviation-civile.gouv.fr/media/dvd",
    ) == (
        "https://www.sia.aviation-civile.gouv.fr/media/dvd/eAIP_19_MAR_2026"
        "/FRANCE/AIRAC-2026-03-19/html/eAIP/FR-ENR-4.4-fr-FR.html"
    )


def test_french_products_discovery_does_not_use_current_cycle_for_unlisted_future_cycle():
    html = """
    <ol>
      <li>
        <a href="/zip-eaip-complet-airac-05-26.html">ZIP eAIP Complet AIRAC 05/26</a>
        En vigueur du 14/05/2026 au 10/06/2026 inclus
      </li>
    </ol>
    """

    try:
        _find_french_product_enr44_url(html, CYCLE_2606)
    except Enr44HtmlLinkNotFound:
        pass
    else:
        raise AssertionError("unlisted future cycle should not resolve to the current SIA product")


def test_french_date_token_pads_first_day_of_month():
    cycle = cycle_for_date(date(2026, 10, 1))
    assert "eAIP_01_OCT_2026" in _french_enr44_url(cycle)


def test_fetch_irish_enr44_html_writes_expected_file(tmp_path):
    def fake_download(url: str, dest: Path, timeout: int = 60) -> None:
        dest.write_text(f"<html>{url}</html>", encoding="utf-8")

    with (
        patch(
            "src.sources.foreign_enr44_html._resolve_irish_enr44_url",
            return_value="https://irish.example/AIRAC/2026-03-19-AIRAC/html/eAIP/EI-ENR-4.4-en-IE.html",
        ),
        patch("src.sources.foreign_enr44_html._download_html", side_effect=fake_download),
    ):
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

    with (
        patch(
            "src.sources.foreign_enr44_html._resolve_french_enr44_url",
            return_value=(
                "https://french.example/media/dvd/eAIP_19_MAR_2026"
                "/FRANCE/AIRAC-2026-03-19/html/eAIP/FR-ENR-4.4-fr-FR.html"
            ),
        ),
        patch("src.sources.foreign_enr44_html._download_html", side_effect=fake_download),
    ):
        result = fetch_french_enr44_html(
            CYCLE_2603,
            tmp_path,
            base_url="https://french.example/media/dvd",
        )

    assert result == tmp_path / FRENCH_ENR44_HTML_FILENAME
    assert "https://french.example/media/dvd/eAIP_19_MAR_2026" in result.read_text(encoding="utf-8")


def test_fetch_irish_enr44_html_returns_none_on_http_error(tmp_path):
    err = urllib.error.HTTPError("https://example.test", 404, "not found", hdrs=None, fp=None)

    with patch("src.sources.foreign_enr44_html._resolve_irish_enr44_url", side_effect=err):
        result = fetch_irish_enr44_html(CYCLE_2603, tmp_path)

    assert result is None
    assert not (tmp_path / IRISH_ENR44_HTML_FILENAME).exists()


def test_fetch_french_enr44_html_returns_none_on_url_error(tmp_path):
    err = urllib.error.URLError("connection refused")

    with patch("src.sources.foreign_enr44_html._resolve_french_enr44_url", side_effect=err):
        result = fetch_french_enr44_html(CYCLE_2603, tmp_path)

    assert result is None
    assert not (tmp_path / FRENCH_ENR44_HTML_FILENAME).exists()


def test_fetch_french_enr44_html_returns_none_on_io_error(tmp_path):
    with (
        patch("src.sources.foreign_enr44_html._resolve_french_enr44_url", return_value="https://example.test/fr.html"),
        patch("src.sources.foreign_enr44_html._download_html", side_effect=OSError("disk full")),
    ):
        result = fetch_french_enr44_html(CYCLE_2603, tmp_path)

    assert result is None
    assert not (tmp_path / FRENCH_ENR44_HTML_FILENAME).exists()
