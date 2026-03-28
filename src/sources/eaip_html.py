"""Download UK eAIP HTML files from the NATS AIP download page.

The NATS AIP page lists each AIRAC cycle under a heading in the form
"AIRAC NN/YYYY" (e.g. "AIRAC 02/2026"). Under each heading there is a
paragraph whose link text "Offline HTML Download" points to a zip archive
containing all eAIP pages for that cycle.

# [RULE:EAIP-PAGE-STRUCTURE]
# The heading format "AIRAC NN/YYYY" and link text "Offline HTML Download"
# are publishing conventions of the NATS EAD website.  If NATS changes
# either string this fetcher must be updated.

Once the zip is downloaded:

Required files (error if missing):
  - EG-ENR-3.2-en-GB.html
  - EG-ENR-3.3-en-GB.html
  - EG-ENR-4.1-en-GB.html
  - EG-ENR-4.2-en-GB.html

Pattern-matched files (warning if none found, not an error):
  - EG-AD-2.XXXX-en-GB.html  (one per UK aerodrome, extracted to ad2/ subdir)

After extraction each file's <meta name="EM.effectiveDateStart"> tag is
read and compared against the cycle's effective_date to catch mismatches.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import urllib.request
import zipfile
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.airac import AiracCycle
from src.processing.zip_handler import download_zip

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# [RULE:EAIP-PAGE-STRUCTURE]
_AIP_INDEX_URL = "https://nats-uk.ead-it.com/cms-nats/opencms/en/Publications/AIP/"
_HEADING_PREFIX = "AIRAC "          # h3 heading starts with this
_LINK_TEXT = "Offline HTML Download"  # exact anchor text to match

# Required files: error if any are missing from the zip (matched by basename)
_TARGET_BASENAMES = frozenset([
    "EG-ENR-3.2-en-GB.html",
    "EG-ENR-3.3-en-GB.html",
    "EG-ENR-4.1-en-GB.html",
    "EG-ENR-4.2-en-GB.html",
])

# AD 2.2 aerodrome pages: extracted by pattern (one file per UK aerodrome).
# Matched when basename starts with "EG-AD-2." and ends with "-en-GB.html".
# Not an error if absent — a warning is logged instead.
_AD2_PREFIX = "EG-AD-2."
_AD2_SUFFIX = "-en-GB.html"
_AD2_SUBDIR = "ad2"

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

    Safety guarantee: all target files are staged in a temp directory first.
    Only after every target is confirmed present are they moved into *dest_dir*
    one by one.  If any move fails, all files already committed to *dest_dir*
    are removed and the temp directory is cleaned up, so *dest_dir* is left in
    its original state.

    Returns a dict mapping basename -> extracted Path.
    Raises EaipFetchError if either target is missing from the archive.
    """
    remaining = set(_TARGET_BASENAMES)
    staged: dict[str, Path] = {}

    tmp_dir = Path(tempfile.mkdtemp(dir=dest_dir, prefix=".eaip_tmp_"))
    try:
        with zipfile.ZipFile(zip_buffer) as zf:
            for entry in zf.infolist():
                name = Path(entry.filename).name
                if name in remaining:
                    tmp_path = tmp_dir / name
                    tmp_path.write_bytes(zf.read(entry.filename))
                    staged[name] = tmp_path
                    remaining.discard(name)

        if remaining:
            raise EaipFetchError(
                f"Zip archive is missing expected files: {sorted(remaining)}. "
                "The eAIP archive format may have changed."
            )

        extracted: dict[str, Path] = {}
        try:
            for name, tmp_path in staged.items():
                final_path = dest_dir / name
                shutil.move(str(tmp_path), str(final_path))
                extracted[name] = final_path
        except Exception:
            for committed_path in extracted.values():
                committed_path.unlink(missing_ok=True)
            raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return extracted


def _extract_ad2_pages(zip_buffer: "BytesIO", dest_dir: Path) -> dict[str, Path]:
    """Extract all AD 2.2 aerodrome HTML pages from *zip_buffer* into *dest_dir/ad2/*.

    Files are matched when their basename starts with ``EG-AD-2.`` and ends
    with ``-en-GB.html``.  They are written into a ``ad2/`` subdirectory of
    *dest_dir* so they are kept separate from the ENR files.

    Returns a dict mapping basename -> extracted Path.
    Returns an empty dict (no error) if no AD 2.2 files are found in the zip.
    """
    ad2_dir = dest_dir / _AD2_SUBDIR
    ad2_dir.mkdir(parents=True, exist_ok=True)

    extracted: dict[str, Path] = {}
    tmp_dir = Path(tempfile.mkdtemp(dir=dest_dir, prefix=".ad2_tmp_"))
    try:
        with zipfile.ZipFile(zip_buffer) as zf:
            for entry in zf.infolist():
                name = Path(entry.filename).name
                if name.startswith(_AD2_PREFIX) and name.endswith(_AD2_SUFFIX):
                    tmp_path = tmp_dir / name
                    tmp_path.write_bytes(zf.read(entry.filename))
                    extracted[name] = tmp_path

        committed: dict[str, Path] = {}
        try:
            for name, tmp_path in extracted.items():
                final_path = ad2_dir / name
                shutil.move(str(tmp_path), str(final_path))
                committed[name] = final_path
        except Exception:
            for committed_path in committed.values():
                committed_path.unlink(missing_ok=True)
            raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return committed


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
    """Download and extract eAIP HTML files for *cycle*.

    Extracts four required ENR files (ENR 3.2, 3.3, 4.1, 4.2) plus all
    AD 2.2 aerodrome pages found in the zip.

    Args:
        cycle:         The target AIRAC cycle.
        dest_dir:      Directory where the HTML files will be written.
                       ENR files go directly into dest_dir; AD 2.2 files
                       go into dest_dir/ad2/.  Created if not already present.
        index_url:     Override the AIP index page URL (mainly for testing).
        validate:      When True (default), verify the EM.effectiveDateStart
                       meta tag in each extracted file.
        timeout_index: HTTP timeout (seconds) for the index page fetch.
        timeout_zip:   HTTP timeout (seconds) for the zip download.

    Returns:
        A dict mapping basename -> Path for every extracted file
        (both ENR and AD 2.2 files).

    Raises:
        EaipFetchError: on any network, structure, or validation failure.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 1. Fetch and parse the index page
    logger.info("Fetching AIP index page: %s", index_url)
    page_html = _fetch_html(index_url, timeout=timeout_index)
    logger.info("AIP index page fetched (%d bytes)", len(page_html))

    # 2. Locate the download URL for this cycle
    zip_url = _find_download_url(page_html, cycle, page_base_url=index_url)
    logger.info("Resolved eAIP zip URL: %s", zip_url)

    # 3. Download the zip
    zip_buffer = download_zip(zip_url, timeout=timeout_zip)
    logger.info("eAIP zip downloaded (%d bytes)", zip_buffer.getbuffer().nbytes)

    # 4a. Extract required ENR files (error if any are missing)
    zip_buffer.seek(0)
    extracted = _extract_targets(zip_buffer, dest_dir)
    for name, path in extracted.items():
        logger.info("Extracted %s (%d bytes)", name, path.stat().st_size)

    # 4b. Extract AD 2.2 aerodrome pages (warning only if none found)
    zip_buffer.seek(0)
    ad2_files = _extract_ad2_pages(zip_buffer, dest_dir)
    if ad2_files:
        logger.info("Extracted %d AD 2.2 aerodrome pages into %s/ad2/", len(ad2_files), dest_dir)
        extracted.update(ad2_files)
    else:
        logger.warning(
            "No AD 2.2 aerodrome pages (EG-AD-2.*-en-GB.html) found in zip. "
            "The eAIP archive format may have changed."
        )

    # 5. Validate effective dates for all extracted files
    if validate:
        for name, path in extracted.items():
            _validate_effective_date(path, cycle.effective_date)
            logger.info("Validated effective date for %s: %s", name, cycle.effective_date.isoformat())
    else:
        logger.info("Effective date validation skipped (validate=False)")

    return extracted
