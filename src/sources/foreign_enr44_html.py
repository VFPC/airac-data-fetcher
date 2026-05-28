"""Fetch non-UK ENR 4.4 HTML support files for FIR-boundary evidence.

These files are source inputs for downstream SRD/AIP reconciliation work. They
are deliberately non-fatal: foreign AIP publication pages can lag briefly during
AIRAC turnover, and a missing support file must not block the UK source fetch.
"""

from __future__ import annotations

import logging
import shutil
import urllib.error
import urllib.request
from pathlib import Path

from src.airac import AiracCycle

logger = logging.getLogger(__name__)

# [RULE:IRISH-EAIP-ENR44-HTML-URL]
IRISH_HTML_BASE_URL = "https://www.airnav.ie/AIRAC"
# [RULE:FRENCH-EAIP-ENR44-HTML-URL]
FRENCH_HTML_BASE_URL = "https://www.sia.aviation-civile.gouv.fr/media/dvd"

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
    timeout: int = 60,
) -> Path | None:
    """Fetch EI-ENR-4.4-en-IE.html for *cycle* into *dest_dir*."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = _irish_enr44_url(cycle, base_url=base_url)
    dest = dest_dir / IRISH_ENR44_HTML_FILENAME
    logger.info("Fetching Irish ENR 4.4 HTML: %s", url)
    return _fetch_enr44_html(url, dest, "Irish", timeout=timeout)


def fetch_french_enr44_html(
    cycle: AiracCycle,
    dest_dir: Path,
    *,
    base_url: str = FRENCH_HTML_BASE_URL,
    timeout: int = 60,
) -> Path | None:
    """Fetch FR-ENR-4.4-fr-FR.html for *cycle* into *dest_dir*."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = _french_enr44_url(cycle, base_url=base_url)
    dest = dest_dir / FRENCH_ENR44_HTML_FILENAME
    logger.info("Fetching French ENR 4.4 HTML: %s", url)
    return _fetch_enr44_html(url, dest, "French", timeout=timeout)
