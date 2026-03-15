"""Download UK eAIP ENR-3.2 and ENR-3.3 HTML files from the NATS AIP download page.

The NATS AIP page lists each AIRAC cycle under a heading in the form
"AIRAC NN/YYYY" (e.g. "AIRAC 02/2026"). Under each heading there is a
paragraph whose link text "Offline HTML Download" points to a zip archive
containing all eAIP pages for that cycle.

# [RULE:EAIP-PAGE-STRUCTURE]
# The heading format "AIRAC NN/YYYY" and link text "Offline HTML Download"
# are publishing conventions of the NATS EAD website.  If NATS changes
# either string this fetcher must be updated.

Once the zip is downloaded, the two target files are located by basename
regardless of their path within the archive:
  - EG-ENR-3.2-en-GB.html
  - EG-ENR-3.3-en-GB.html

After extraction each file's <meta name="EM.effectiveDateStart"> tag is
read and compared against the cycle's effective_date to catch mismatches.
"""

from __future__ import annotations

import urllib.request
import zipfile
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.airac import AiracCycle
from src.processing.zip_handler import download_zip

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# [RULE:EAIP-PAGE-STRUCTURE]
_AIP_INDEX_URL = "https://nats-uk.ead-it.com/cms-nats/opencms/en/Publication/AIP/"
_HEADING_PREFIX = "AIRAC "          # h3 heading starts with this
_LINK_TEXT = "Offline HTML Download"  # exact anchor text to match

# The two filenames we need from the zip (matched by basename only)
_TARGET_BASENAMES = frozenset([
    "EG-ENR-3.2-en-GB.html",
    "EG-ENR-3.3-en-GB.html",
])

_META_EFFECTIVE_DATE = "EM.effectiveDateStart"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class EaipFetchError(Exception):
    """Raised when any step of the eAIP fetch/validate pipeline fails."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_html(url: str, timeout: int = 30) -> str:
    """Fetch *url* and return the response body as a UTF-8 string."""
    req = urllib.request.Request(url, headers={"User-Agent": "airac-data-fetcher/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _cycle_heading_text(cycle: AiracCycle) -> str:
    """Return the h3 heading text for *cycle*, e.g. 'AIRAC 02/2026'.

    # [RULE:EAIP-PAGE-STRUCTURE]
    """
    return f"{_HEADING_PREFIX}{cycle.number:02d}/{cycle.year}"


def _find_download_url(page_html: str, cycle: AiracCycle, page_base_url: str) -> str:
    """Parse *page_html* and return the absolute URL for *cycle*'s offline zip.

    Raises EaipFetchError if the heading or link cannot be found.
    """
    soup = BeautifulSoup(page_html, "html.parser")
    heading_text = _cycle_heading_text(cycle)

    # Walk h3 tags to find the matching cycle heading
    target_h3 = None
    for h3 in soup.find_all("h3"):
        if h3.get_text(strip=True).startswith(heading_text):
            target_h3 = h3
            break

    if target_h3 is None:
        raise EaipFetchError(
            f"Could not find heading '{heading_text}' on AIP page. "
            f"Check {_AIP_INDEX_URL} — the page structure may have changed "
            f"[RULE:EAIP-PAGE-STRUCTURE]."
        )

    # Walk siblings after the heading until the next h3 to find the link
    for sibling in target_h3.find_next_siblings():
        if sibling.name == "h3":
            break  # moved past this cycle's section
        if sibling.name in ("p", "div"):
            link = sibling.find("a", string=lambda t: t and t.strip() == _LINK_TEXT)
            if link and link.get("href"):
                href = link["href"].strip()
                if href.startswith("http"):
                    return href
                return urljoin(page_base_url, href)

    raise EaipFetchError(
        f"Found heading '{heading_text}' but could not find '{_LINK_TEXT}' link. "
        f"Check {_AIP_INDEX_URL} — the page structure may have changed "
        f"[RULE:EAIP-PAGE-STRUCTURE]."
    )



def _extract_targets(zip_buffer: BytesIO, dest_dir: Path) -> dict[str, Path]:
    """Extract the two target HTML files from *zip_buffer* into *dest_dir*.

    Files are located by basename regardless of their path within the archive.
    Returns a dict mapping basename -> extracted Path.
    Raises EaipFetchError if either target is missing from the archive.
    """
    remaining = set(_TARGET_BASENAMES)
    extracted: dict[str, Path] = {}

    with zipfile.ZipFile(zip_buffer) as zf:
        for entry in zf.infolist():
            name = Path(entry.filename).name
            if name in remaining:
                dest_path = dest_dir / name
                dest_path.write_bytes(zf.read(entry.filename))
                extracted[name] = dest_path
                remaining.discard(name)

    if remaining:
        raise EaipFetchError(
            f"Zip archive is missing expected files: {sorted(remaining)}. "
            "The eAIP archive format may have changed."
        )
    return extracted


def _validate_effective_date(html_path: Path, expected: date) -> None:
    """Read the EM.effectiveDateStart meta tag from *html_path* and verify it
    matches *expected*.

    Raises EaipFetchError on mismatch or if the tag is absent.
    """
    content = html_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(content, "html.parser")
    meta = soup.find("meta", attrs={"name": _META_EFFECTIVE_DATE})
    if meta is None:
        raise EaipFetchError(
            f"{html_path.name}: missing <meta name='{_META_EFFECTIVE_DATE}'> tag."
        )
    raw = meta.get("content", "").strip()
    try:
        found = date.fromisoformat(raw)
    except ValueError as exc:
        raise EaipFetchError(
            f"{html_path.name}: could not parse '{_META_EFFECTIVE_DATE}' "
            f"content '{raw}' as ISO date."
        ) from exc

    if found != expected:
        raise EaipFetchError(
            f"{html_path.name}: effective date mismatch — "
            f"file says {found.isoformat()}, expected {expected.isoformat()}."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_eaip_html(
    cycle: AiracCycle,
    dest_dir: Path,
    *,
    index_url: str = _AIP_INDEX_URL,
    validate: bool = True,
    timeout_index: int = 30,
    timeout_zip: int = 120,
) -> dict[str, Path]:
    """Download and extract the eAIP ENR-3.2 and ENR-3.3 HTML files for *cycle*.

    Args:
        cycle:         The target AIRAC cycle.
        dest_dir:      Directory where the HTML files will be written.
                       Created if it does not already exist.
        index_url:     Override the AIP index page URL (mainly for testing).
        validate:      When True (default), verify the EM.effectiveDateStart
                       meta tag in each extracted file.
        timeout_index: HTTP timeout (seconds) for the index page fetch.
        timeout_zip:   HTTP timeout (seconds) for the zip download.

    Returns:
        A dict mapping basename -> Path for each extracted file.

    Raises:
        EaipFetchError: on any network, structure, or validation failure.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 1. Fetch and parse the index page
    page_html = _fetch_html(index_url, timeout=timeout_index)

    # 2. Locate the download URL for this cycle
    zip_url = _find_download_url(page_html, cycle, page_base_url=index_url)

    # 3. Download the zip
    zip_buffer = download_zip(zip_url, timeout=timeout_zip)

    # 4. Extract target files
    extracted = _extract_targets(zip_buffer, dest_dir)

    # 5. Validate effective dates
    if validate:
        for path in extracted.values():
            _validate_effective_date(path, cycle.effective_date)

    return extracted
