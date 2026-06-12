"""Download the EUROCONTROL Route Availability Document (RAD) Excel workbook.

The RAD is published by EUROCONTROL at https://www.nm.eurocontrol.int/RAD/.
The index page lists workbooks as relative href links, e.g.:
  assets/AIRAC-RAD_DATA/CURRENT_AIRAC/RAD_2606_v1_12.xlsx
  assets/AIRAC-RAD_DATA/AIRAC+1/RAD_2607_v1_0.xlsx

The version component (v{M}_{N}) is NOT cycle-deterministic — it increments
with each EUROCONTROL revision.  The fetcher scrapes the index page to discover
the URL, then downloads the workbook directly (no zip wrapping).

# [RULE:RAD-DOWNLOAD-URL]
# Base URL:  https://www.nm.eurocontrol.int/RAD/
# Index URL: https://www.nm.eurocontrol.int/RAD/index.html
# Workbook hrefs are relative to the base URL and follow the pattern:
#   assets/AIRAC-RAD_DATA/{bucket}/RAD_{YYNN}_v{M}_{N}.xlsx
# where {bucket} is typically CURRENT_AIRAC or AIRAC+1.
# If EUROCONTROL changes the index page structure or the href pattern,
# update _RAD_WORKBOOK_RE and/or _find_workbook_url() here.
"""

from __future__ import annotations

import logging
import re
import tempfile
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.airac import AiracCycle

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# [RULE:RAD-DOWNLOAD-URL]
_RAD_BASE_URL = "https://www.nm.eurocontrol.int/RAD/"
_RAD_INDEX_URL = _RAD_BASE_URL + "index.html"

# Matches workbook basenames like RAD_2606_v1_12.xlsx.
# The end anchor intentionally requires a path-style href with no query string.
# If EUROCONTROL adds query strings or fragments, update this regex.
# Group 1: cycle ident (e.g. "2606")
# Group 2: major version (e.g. "1")
# Group 3: minor version (e.g. "12")
_RAD_WORKBOOK_RE = re.compile(
    r"RAD_(\d{4})_v(\d+)_(\d+)\.xlsx$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class RadFetchError(Exception):
    """Raised when any step of the RAD fetch pipeline fails."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_index_html(index_url: str, timeout: int) -> str:
    """Fetch the RAD index page and return the raw HTML string.

    # [RULE:RAD-DOWNLOAD-URL]
    """
    req = urllib.request.Request(
        index_url,
        headers={"User-Agent": "airac-data-fetcher/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RadFetchError(
            f"HTTP {exc.code} fetching RAD index: {index_url} "
            "[RULE:RAD-DOWNLOAD-URL]"
        ) from exc
    except urllib.error.URLError as exc:
        raise RadFetchError(
            f"Network error fetching RAD index: {exc.reason}"
        ) from exc


def _find_workbook_url(html: str, cycle: AiracCycle, base_url: str) -> str:
    """Parse the RAD index HTML and return the absolute download URL for *cycle*.

    Searches all <a href> links for a workbook filename matching
    ``RAD_{cycle.ident}_v{M}_{N}.xlsx``.  If multiple versions are found
    (e.g. both CURRENT_AIRAC and AIRAC+1 buckets list the same cycle during a
    transition period), the highest version number wins.

    # [RULE:RAD-DOWNLOAD-URL]
    Raises RadFetchError if no matching link is found.
    """
    soup = BeautifulSoup(html, "html.parser")

    candidates: list[tuple[int, int, str]] = []
    for tag in soup.find_all("a", href=True):
        href: str = tag["href"]
        m = _RAD_WORKBOOK_RE.search(href)
        if not m:
            continue
        if m.group(1) != cycle.ident:
            continue
        major, minor = int(m.group(2)), int(m.group(3))
        full_url = urljoin(base_url, href)
        candidates.append((major, minor, full_url))
        logger.debug("RAD candidate: %s (v%d_%d)", full_url, major, minor)

    if not candidates:
        raise RadFetchError(
            f"No RAD workbook found for cycle {cycle.ident} on the index page. "
            "EUROCONTROL may have changed the page structure. "
            "[RULE:RAD-DOWNLOAD-URL]"
        )

    candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
    _, _, chosen_url = candidates[0]
    logger.info("Selected RAD workbook URL: %s", chosen_url)
    return chosen_url


def _download_workbook(url: str, dest_dir: Path, timeout: int) -> Path:
    """Download the workbook at *url* into *dest_dir* atomically.

    The file is written to a temp location first, then moved into *dest_dir*
    only on success, so *dest_dir* is never left with a partial file.

    Returns the final destination path.
    """
    basename = url.rsplit("/", 1)[-1]
    final_path = dest_dir / basename

    tmp_dir = Path(tempfile.mkdtemp(dir=dest_dir, prefix=".rad_tmp_"))
    tmp_path = tmp_dir / basename
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "airac-data-fetcher/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                tmp_path.write_bytes(resp.read())
        except urllib.error.HTTPError as exc:
            raise RadFetchError(
                f"HTTP {exc.code} downloading RAD workbook: {url}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RadFetchError(
                f"Network error downloading RAD workbook: {exc.reason}"
            ) from exc

        shutil.move(str(tmp_path), str(final_path))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return final_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_rad(
    cycle: AiracCycle,
    dest_dir: Path,
    *,
    index_url: str = _RAD_INDEX_URL,
    timeout_page: int = 30,
    timeout_download: int = 120,
) -> Path:
    """Download the RAD Excel workbook for *cycle* into *dest_dir*.

    Args:
        cycle:            The target AIRAC cycle.
        dest_dir:         Directory where the workbook will be written.
                          Created if it does not already exist.
        index_url:        Override the RAD index URL (for testing).
        timeout_page:     HTTP timeout in seconds for the index page fetch.
        timeout_download: HTTP timeout in seconds for the workbook download.

    Returns:
        Path to the downloaded ``.xlsx`` file.

    Raises:
        RadFetchError: on any network, parsing, or missing-file failure.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Fetching RAD index: %s", index_url)
    base_url = index_url.rsplit("/", 1)[0] + "/"
    html = _fetch_index_html(index_url, timeout=timeout_page)

    workbook_url = _find_workbook_url(html, cycle, base_url)

    workbook_path = _download_workbook(workbook_url, dest_dir, timeout=timeout_download)
    logger.info(
        "RAD workbook downloaded: %s (%d bytes)",
        workbook_path.name,
        workbook_path.stat().st_size,
    )
    return workbook_path
