"""Download the NATS Standard Route Document (SRD) Excel file for an AIRAC cycle.

The SRD zip URL is fully deterministic from the cycle object — no page
scraping is needed.

# [RULE:SRD-DOWNLOAD-URL]
# URL pattern: {_SRD_BASE}AIRAC-{NN}-{YYYY}.zip
# where NN is the zero-padded cycle number and YYYY is the 4-digit year.
# Confirmed from live page: AIRAC-02-2026.zip and AIRAC-03-2026.zip visible
# simultaneously for the current and next cycle (as of 2026-03-10).
# If NATS changes the base path or filename pattern, update _SRD_BASE and/or
# _srd_zip_url() here.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import urllib.error
import zipfile
from pathlib import Path

from src.airac import AiracCycle
from src.processing.zip_handler import download_zip

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# [RULE:SRD-DOWNLOAD-URL]
_SRD_BASE = (
    "https://nats-uk.ead-it.com"
    "/cms-nats/export/sites/default/en/Publications/digital-datasets/SRD/"
)

# Excel extensions that could appear in the zip
_EXCEL_EXTENSIONS = frozenset([".xlsx", ".xls"])


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SrdFetchError(Exception):
    """Raised when any step of the SRD fetch pipeline fails."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _srd_zip_url(cycle: AiracCycle) -> str:
    """Return the direct download URL for *cycle*'s SRD zip.

    # [RULE:SRD-DOWNLOAD-URL]
    """
    return f"{_SRD_BASE}AIRAC-{cycle.number:02d}-{cycle.year}.zip"


def _extract_excel(zip_buffer: BytesIO, dest_dir: Path) -> dict[str, Path]:
    """Extract all Excel files from *zip_buffer* into *dest_dir*.

    Files are identified by extension (.xlsx / .xls) regardless of their
    path within the archive.

    Safety guarantee: all Excel files are staged in a temp directory first.
    Only after at least one is confirmed present are they moved into *dest_dir*
    one by one.  If any move fails, all files already committed to *dest_dir*
    are removed and the temp directory is cleaned up, so *dest_dir* is left in
    its original state.

    Returns a dict mapping basename -> extracted Path.
    Raises SrdFetchError if no Excel file is found in the archive.
    """
    staged: dict[str, Path] = {}

    tmp_dir = Path(tempfile.mkdtemp(dir=dest_dir, prefix=".srd_tmp_"))
    try:
        with zipfile.ZipFile(zip_buffer) as zf:
            for entry in zf.infolist():
                suffix = Path(entry.filename).suffix.lower()
                if suffix in _EXCEL_EXTENSIONS:
                    basename = Path(entry.filename).name
                    tmp_path = tmp_dir / basename
                    tmp_path.write_bytes(zf.read(entry.filename))
                    staged[basename] = tmp_path

        if not staged:
            raise SrdFetchError(
                "SRD zip contained no Excel files (.xlsx / .xls). "
                "The archive format may have changed."
            )

        extracted: dict[str, Path] = {}
        try:
            for basename, tmp_path in staged.items():
                final_path = dest_dir / basename
                shutil.move(str(tmp_path), str(final_path))
                extracted[basename] = final_path
        except Exception:
            for committed_path in extracted.values():
                committed_path.unlink(missing_ok=True)
            raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return extracted


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_srd(
    cycle: AiracCycle,
    dest_dir: Path,
    *,
    timeout: int = 120,
) -> dict[str, Path]:
    """Download and extract the SRD Excel file(s) for *cycle*.

    Args:
        cycle:    The target AIRAC cycle.
        dest_dir: Directory where the Excel file(s) will be written.
                  Created if it does not already exist.
        timeout:  HTTP timeout in seconds for the zip download.

    Returns:
        A dict mapping basename -> Path for each extracted Excel file.

    Raises:
        SrdFetchError: on any network or extraction failure.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    url = _srd_zip_url(cycle)
    logger.info("Fetching SRD zip: %s", url)
    try:
        zip_buffer = download_zip(url, timeout=timeout)
    except urllib.error.HTTPError as exc:
        logger.error("HTTP %d fetching SRD zip: %s", exc.code, url)
        raise SrdFetchError(
            f"HTTP {exc.code} fetching SRD zip: {url}\n"
            "The URL pattern may have changed — check the NATS Digital Datasets page "
            "and update _SRD_BASE / _srd_zip_url() if needed. [RULE:SRD-DOWNLOAD-URL]"
        ) from exc
    except urllib.error.URLError as exc:
        logger.error("Network error fetching SRD zip: %s", exc.reason)
        raise SrdFetchError(f"Network error fetching SRD zip: {exc.reason}") from exc

    logger.info("SRD zip downloaded (%d bytes)", zip_buffer.getbuffer().nbytes)
    extracted = _extract_excel(zip_buffer, dest_dir)
    for name, path in extracted.items():
        logger.info("Extracted %s (%d bytes)", name, path.stat().st_size)
    return extracted
