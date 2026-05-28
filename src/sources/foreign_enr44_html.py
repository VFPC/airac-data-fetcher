"""Fetch non-UK ENR 4.4 HTML support files for FIR-boundary evidence.

These files are source inputs for downstream SRD/AIP reconciliation work. They
are deliberately non-fatal: foreign AIP publication pages can lag briefly during
AIRAC turnover, and a missing support file must not block the UK source fetch.
"""

from __future__ import annotations

import logging
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

from src.airac import AiracCycle

logger = logging.getLogger(__name__)

# [RULE:IRISH-EAIP-ENR44-HTML-URL]
IRISH_HTML_BASE_URL = "https://www.airnav.ie/AIRAC"
# [RULE:FRENCH-EAIP-ENR44-HTML-URL]
FRENCH_HTML_BASE_URL = "https://www.sia.aviation-civile.gouv.fr/media/dvd"
FRENCH_EAIP_PRODUCTS_URL = (
    "https://www.sia.aviation-civile.gouv.fr"
    "/produits-numeriques-en-libre-disposition/eaip.html"
)

IRISH_ENR44_HTML_FILENAME = "EI-ENR-4.4-en-IE.html"
FRENCH_ENR44_HTML_FILENAME = "FR-ENR-4.4-fr-FR.html"
_MONTH_TOKENS = (
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)


class Enr44HtmlLinkNotFound(Exception):
    """Raised when a provider page does not expose the target cycle's ENR 4.4 link."""


def _strip_slash(url: str) -> str:
    return url.rstrip("/")


def _french_date_token(cycle: AiracCycle) -> str:
    effective = cycle.effective_date
    return f"{effective.day:02d}_{_MONTH_TOKENS[effective.month - 1]}_{effective.year}"


def _irish_enr44_url(
    cycle: AiracCycle,
    base_url: str = IRISH_HTML_BASE_URL,
) -> str:
    """Return the AirNav Ireland cycle ENR 4.4 HTML URL for *cycle*."""
    effective = cycle.effective_date.isoformat()
    return (
        f"{_strip_slash(base_url)}/{effective}-AIRAC/html/eAIP/"
        f"{IRISH_ENR44_HTML_FILENAME}"
    )


def _irish_portal_url(base_url: str = IRISH_HTML_BASE_URL) -> str:
    return f"{_strip_slash(base_url)}/index.html"


def _french_enr44_url(
    cycle: AiracCycle,
    base_url: str = FRENCH_HTML_BASE_URL,
) -> str:
    """Return the SIA France cycle ENR 4.4 HTML URL for *cycle*."""
    effective = cycle.effective_date.isoformat()
    return (
        f"{_strip_slash(base_url)}/eAIP_{_french_date_token(cycle)}"
        f"/FRANCE/AIRAC-{effective}/html/eAIP/{FRENCH_ENR44_HTML_FILENAME}"
    )


def _effective_token(cycle: AiracCycle) -> str:
    return f"{cycle.effective_date.day:02d} {_MONTH_TOKENS[cycle.effective_date.month - 1]} {cycle.year}"


def _looks_like_cycle_heading(text: str) -> bool:
    return "AIRAC" in text and "EFF " in text


def _french_cycle_token(cycle: AiracCycle) -> str:
    return f"{cycle.number:02d}/{cycle.year % 100:02d}"


def _fetch_text(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _find_irish_eaip_enr44_url(
    portal_html: str,
    cycle: AiracCycle,
    portal_url: str,
) -> str:
    """Return the target-cycle Irish ENR 4.4 HTML URL from the AirNav portal."""
    soup = BeautifulSoup(portal_html, "html.parser")
    needle = f"EFF {_effective_token(cycle)}"

    for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
        heading_text = heading.get_text(" ", strip=True).upper()
        if needle not in heading_text:
            continue

        for sibling in heading.next_siblings:
            sibling_name = getattr(sibling, "name", None)
            if sibling_name in {"h1", "h2", "h3", "h4"}:
                sibling_text = sibling.get_text(" ", strip=True).upper()
                if _looks_like_cycle_heading(sibling_text):
                    break
            if not hasattr(sibling, "find_all"):
                continue
            links = sibling.find_all("a", href=True)
            if sibling_name == "a" and sibling.get("href"):
                links = [sibling]
            for link in links:
                if "EAIP" in link.get_text(" ", strip=True).upper():
                    index_url = urllib.parse.urljoin(portal_url, link["href"])
                    return index_url.rsplit("/", 1)[0] + f"/eAIP/{IRISH_ENR44_HTML_FILENAME}"

    raise Enr44HtmlLinkNotFound(
        f"AirNav Ireland portal does not expose eAIP HTML for AIRAC {cycle.ident} "
        f"({cycle.effective_date.isoformat()})."
    )


def _resolve_irish_enr44_url(
    cycle: AiracCycle,
    *,
    base_url: str = IRISH_HTML_BASE_URL,
    timeout: int = 30,
) -> str:
    portal_url = _irish_portal_url(base_url)
    portal_html = _fetch_text(portal_url, timeout=timeout)
    return _find_irish_eaip_enr44_url(portal_html, cycle, portal_url)


def _find_french_product_enr44_url(
    products_html: str,
    cycle: AiracCycle,
    *,
    base_url: str = FRENCH_HTML_BASE_URL,
) -> str:
    """Return the target-cycle French ENR 4.4 HTML URL if the SIA page lists it."""
    soup = BeautifulSoup(products_html, "html.parser")
    cycle_token = _french_cycle_token(cycle)
    effective_fr = cycle.effective_date.strftime("%d/%m/%Y")

    for link in soup.find_all("a", href=True):
        link_text = link.get_text(" ", strip=True).upper()
        if "ZIP EAIP COMPLET" not in link_text or f"AIRAC {cycle_token}" not in link_text:
            continue

        block = link.find_parent(["li", "div", "article"]) or link.parent
        block_text = block.get_text(" ", strip=True) if block else link_text
        if effective_fr not in block_text:
            continue

        return _french_enr44_url(cycle, base_url=base_url)

    raise Enr44HtmlLinkNotFound(
        f"SIA France eAIP products page does not list AIRAC {cycle.ident} "
        f"({cycle.effective_date.isoformat()})."
    )


def _resolve_french_enr44_url(
    cycle: AiracCycle,
    *,
    base_url: str = FRENCH_HTML_BASE_URL,
    products_url: str = FRENCH_EAIP_PRODUCTS_URL,
    timeout: int = 30,
) -> str:
    products_html = _fetch_text(products_url, timeout=timeout)
    return _find_french_product_enr44_url(products_html, cycle, base_url=base_url)


def _download_html(url: str, dest: Path, timeout: int = 60) -> None:
    """Download text/html from *url* and write it atomically to *dest*."""
    tmp_path = dest.with_suffix(dest.suffix + ".tmp")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            tmp_path.write_bytes(resp.read())
        shutil.move(str(tmp_path), str(dest))
    finally:
        tmp_path.unlink(missing_ok=True)


def _fetch_enr44_html(url: str, dest: Path, label: str, timeout: int = 60) -> Path | None:
    try:
        _download_html(url, dest, timeout=timeout)
    except urllib.error.HTTPError as exc:
        logger.warning("HTTP %d fetching %s ENR 4.4 HTML - skipped: %s", exc.code, label, url)
        return None
    except urllib.error.URLError as exc:
        logger.warning("Network error fetching %s ENR 4.4 HTML - skipped: %s", label, exc.reason)
        return None
    except OSError as exc:
        logger.warning("I/O error writing %s ENR 4.4 HTML - skipped: %s", label, exc)
        return None

    logger.info("%s ENR 4.4 HTML written to %s (%d bytes)", label, dest, dest.stat().st_size)
    return dest


def fetch_irish_enr44_html(
    cycle: AiracCycle,
    dest_dir: Path,
    *,
    base_url: str = IRISH_HTML_BASE_URL,
    page_timeout: int = 30,
    timeout: int = 60,
) -> Path | None:
    """Fetch EI-ENR-4.4-en-IE.html for *cycle* into *dest_dir*."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        url = _resolve_irish_enr44_url(cycle, base_url=base_url, timeout=page_timeout)
    except Enr44HtmlLinkNotFound as exc:
        logger.warning("%s", exc)
        return None
    except urllib.error.HTTPError as exc:
        logger.warning("HTTP %d fetching Irish AIRAC portal - ENR 4.4 HTML skipped", exc.code)
        return None
    except urllib.error.URLError as exc:
        logger.warning("Network error fetching Irish AIRAC portal - ENR 4.4 HTML skipped: %s", exc.reason)
        return None
    dest = dest_dir / IRISH_ENR44_HTML_FILENAME
    logger.info("Fetching Irish ENR 4.4 HTML: %s", url)
    return _fetch_enr44_html(url, dest, "Irish", timeout=timeout)


def fetch_french_enr44_html(
    cycle: AiracCycle,
    dest_dir: Path,
    *,
    base_url: str = FRENCH_HTML_BASE_URL,
    products_url: str = FRENCH_EAIP_PRODUCTS_URL,
    page_timeout: int = 30,
    timeout: int = 60,
) -> Path | None:
    """Fetch FR-ENR-4.4-fr-FR.html for *cycle* into *dest_dir*."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        url = _resolve_french_enr44_url(
            cycle,
            base_url=base_url,
            products_url=products_url,
            timeout=page_timeout,
        )
    except Enr44HtmlLinkNotFound as exc:
        logger.warning("%s", exc)
        return None
    except urllib.error.HTTPError as exc:
        logger.warning("HTTP %d fetching SIA eAIP products page - ENR 4.4 HTML skipped", exc.code)
        return None
    except urllib.error.URLError as exc:
        logger.warning("Network error fetching SIA eAIP products page - ENR 4.4 HTML skipped: %s", exc.reason)
        return None
    dest = dest_dir / FRENCH_ENR44_HTML_FILENAME
    logger.info("Fetching French ENR 4.4 HTML: %s", url)
    return _fetch_enr44_html(url, dest, "French", timeout=timeout)
