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

import urllib.error
import zipfile
from pathlib import Path

from src.airac import AiracCycle
from src.processing.zip_handler import download_zip

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

    Returns a dict mapping basename -> extracted Path.
    Raises SrdFetchError if no Excel file is found in the archive.
    """
    extracted: dict[str, Path] = {}

    with zipfile.ZipFile(zip_buffer) as zf:
        for entry in zf.infolist():
            suffix = Path(entry.filename).suffix.lower()
            if suffix in _EXCEL_EXTENSIONS:
                basename = Path(entry.filename).name
                dest_path = dest_dir / basename
                dest_path.write_bytes(zf.read(entry.filename))
                extracted[basename] = dest_path

    if not extracted:
        raise SrdFetchError(
            "SRD zip contained no Excel files (.xlsx / .xls). "
            "The archive format may have changed."
        )
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
    try:
        zip_buffer = download_zip(url, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise SrdFetchError(
            f"HTTP {exc.code} fetching SRD zip: {url}\n"
            "The URL pattern may have changed — check the NATS Digital Datasets page "
            "and update _SRD_BASE / _srd_zip_url() if needed. [RULE:SRD-DOWNLOAD-URL]"
        ) from exc
    except urllib.error.URLError as exc:
        raise SrdFetchError(f"Network error fetching SRD zip: {exc.reason}") from exc

    return _extract_excel(zip_buffer, dest_dir)
