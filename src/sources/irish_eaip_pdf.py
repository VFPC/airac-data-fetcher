"""Download EI_ENR_4_4_EN.pdf from the AirNav Ireland IAIP package page.

The Irish eAIP publishes each section as a GUID-based PDF link:

    https://www.airnav.ie/getattachment/{GUID}/EI_ENR_4_4_EN.pdf

The GUID is not deterministic — it changes whenever AirNav replaces the
document (typically once per AIRAC cycle, sometimes mid-cycle if an interim
amendment is issued).  The stable entry point is the IAIP package page:

    # [RULE:IRISH-EAIP-ENR44-URL]
    https://www.airnav.ie/air-traffic-management/aeronautical-information-management/aip-package

The page is fetched as static HTML (no JS rendering required — the ENR
links are present in the raw markup).  The GUID is extracted by regex and
the PDF downloaded directly.

Because the Irish AIP is an external dependency outside our control, all
errors are non-fatal: a warning is logged and the overall fetch continues.
The GUID that was downloaded is logged so that re-runs can detect whether
AirNav has issued a replacement document mid-cycle.
"""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# [RULE:IRISH-EAIP-ENR44-URL]
_IAIP_PACKAGE_URL = (
    "https://www.airnav.ie"
    "/air-traffic-management/aeronautical-information-management/aip-package"
)
_BASE_URL = "https://www.airnav.ie"

# Regex to locate the ENR 4.4 PDF link within the page HTML.
# Matches: getattachment/{GUID}/EI_ENR_4_4_EN.pdf
# [RULE:IRISH-EAIP-ENR44-URL]
_ENR44_LINK_RE = re.compile(
    r"getattachment/([\w\-]+)/EI_ENR_4_4_EN\.pdf"
)

PDF_FILENAME = "EI_ENR_4_4_EN.pdf"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class IrishEaipFetchError(Exception):
    """Raised when the Irish eAIP ENR 4.4 fetch fails unrecoverably."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_page(url: str, timeout: int = 30) -> str:
    """Return the HTML text of *url*."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _find_enr44_url(page_html: str, base_url: str = _BASE_URL) -> tuple[str, str]:
    """Return (absolute_pdf_url, guid) for EI_ENR_4_4_EN.pdf in *page_html*.

    Raises IrishEaipFetchError if the link is not found.
    """
    m = _ENR44_LINK_RE.search(page_html)
    if not m:
        raise IrishEaipFetchError(
            "Could not find EI_ENR_4_4_EN.pdf link on the IAIP package page. "
            "AirNav may have restructured the page. [RULE:IRISH-EAIP-ENR44-URL]"
        )
    guid = m.group(1)
    url = f"{base_url}/getattachment/{guid}/EI_ENR_4_4_EN.pdf?lang=en-IE"
    return url, guid


def _download_pdf(url: str, dest: Path, timeout: int = 60) -> None:
    """Download *url* and write bytes atomically to *dest*.

    Uses a sibling temp file so the destination is either fully written
    or absent — never partially written.
    """
    tmp_path = dest.with_suffix(".pdf.tmp")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            tmp_path.write_bytes(resp.read())
        shutil.move(str(tmp_path), str(dest))
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_irish_enr44(
    dest_dir: Path,
    *,
    page_url: str = _IAIP_PACKAGE_URL,
    page_timeout: int = 30,
    pdf_timeout: int = 60,
) -> Path | None:
    """Download EI_ENR_4_4_EN.pdf into *dest_dir*.

    Returns the Path to the downloaded file on success, or None if the
    fetch fails (warning is logged; the overall pipeline is not aborted).

    Args:
        dest_dir:     Directory where EI_ENR_4_4_EN.pdf will be written.
                      Created if it does not exist.
        page_url:     URL of the AirNav Ireland IAIP package page.
                      Override for testing or if AirNav changes the URL.
        page_timeout: HTTP timeout in seconds for the index page fetch.
        pdf_timeout:  HTTP timeout in seconds for the PDF download.

    The GUID embedded in the download URL is logged at INFO level so that
    re-runs within the same cycle can detect whether AirNav has silently
    replaced the document (e.g. an interim amendment).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / PDF_FILENAME

    try:
        logger.info("Fetching Irish IAIP package page: %s", page_url)
        html = _fetch_page(page_url, timeout=page_timeout)
    except urllib.error.HTTPError as exc:
        logger.warning(
            "HTTP %d fetching Irish IAIP page — EI_ENR_4_4_EN.pdf skipped: %s",
            exc.code, page_url,
        )
        return None
    except urllib.error.URLError as exc:
        logger.warning(
            "Network error fetching Irish IAIP page — EI_ENR_4_4_EN.pdf skipped: %s",
            exc.reason,
        )
        return None

    try:
        pdf_url, guid = _find_enr44_url(html)
    except IrishEaipFetchError as exc:
        logger.warning("%s", exc)
        return None

    logger.info("Found EI_ENR_4_4_EN.pdf (guid=%s): %s", guid, pdf_url)

    try:
        _download_pdf(pdf_url, dest_path, timeout=pdf_timeout)
    except urllib.error.HTTPError as exc:
        logger.warning(
            "HTTP %d downloading EI_ENR_4_4_EN.pdf — skipped: %s", exc.code, pdf_url
        )
        return None
    except urllib.error.URLError as exc:
        logger.warning(
            "Network error downloading EI_ENR_4_4_EN.pdf — skipped: %s", exc.reason
        )
        return None
    except OSError as exc:
        logger.warning("I/O error writing EI_ENR_4_4_EN.pdf — skipped: %s", exc)
        return None

    logger.info(
        "EI_ENR_4_4_EN.pdf written (%d bytes, guid=%s)",
        dest_path.stat().st_size, guid,
    )
    return dest_path
