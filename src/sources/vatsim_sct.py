"""Download the UK sector file (.sct) from VATSIM-UK/uk-controller-pack releases.

Strategy
--------
1. Query the GitHub releases API for VATSIM-UK/uk-controller-pack.
2. Filter releases whose tag matches the target AIRAC cycle.
3. Pick the most recently published matching tag (handles patch letters a/b/c…).
4. Download the source zip for that tag.
5. Extract the SCT file from inside the zip.

Release tag convention
----------------------
# [RULE:SCT-RELEASE-TAG]
Tags follow ``{YYYY}_{NN}`` for base releases and ``{YYYY}_{NN}{letter}`` for
patches, where YYYY is the 4-digit year and NN is the zero-padded cycle number
matching the AIRAC cycle.  Examples: ``2026_02``, ``2026_02a``.

SCT file path convention
------------------------
# [RULE:SCT-FILE-PATH]
Inside the source zip the sector file is at ``UK/data/UK_{YYYY}_{NN}.sct``.
The file is located by matching both the ``UK/data/`` directory component and
the exact basename ``UK_{YYYY}_{NN}.sct``.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from src.airac import AiracCycle
from src.processing.zip_handler import download_zip

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GITHUB_REPO = "VATSIM-UK/uk-controller-pack"
_RELEASES_API = f"https://api.github.com/repos/{_GITHUB_REPO}/releases"
_SOURCE_ZIP_URL = (
    "https://github.com/{repo}/archive/refs/tags/{tag}.zip"
)

# [RULE:SCT-RELEASE-TAG] tag pattern: YYYY_NN with optional lowercase letter(s)
_TAG_RE = re.compile(r"^(\d{4})_(\d{2})([a-z]*)$")

# [RULE:SCT-FILE-PATH] path component and basename inside the source zip
_SCT_DATA_DIR = "UK/data/"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SctFetchError(Exception):
    """Raised when any step of the SCT fetch pipeline fails."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sct_basename(cycle: AiracCycle) -> str:
    """Return the expected SCT filename for *cycle*.

    # [RULE:SCT-FILE-PATH]
    """
    return f"UK_{cycle.year}_{cycle.number:02d}.sct"


def _tag_prefix(cycle: AiracCycle) -> str:
    """Return the base tag prefix for *cycle* (without patch letter).

    # [RULE:SCT-RELEASE-TAG]
    """
    return f"{cycle.year}_{cycle.number:02d}"


def _matches_cycle(tag: str, cycle: AiracCycle) -> bool:
    """Return True if *tag* corresponds to *cycle* (any patch letter).

    # [RULE:SCT-RELEASE-TAG]
    """
    m = _TAG_RE.match(tag)
    if not m:
        return False
    year, num = int(m.group(1)), int(m.group(2))
    return year == cycle.year and num == cycle.number


def _fetch_releases(api_url: str, timeout: int = 30) -> list[dict]:
    """Fetch the GitHub releases list and return it as a list of dicts."""
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": "airac-data-fetcher/1.0",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _latest_tag_for_cycle(releases: list[dict], cycle: AiracCycle) -> str:
    """Return the tag name of the most recently published release for *cycle*.

    # [RULE:SCT-RELEASE-TAG]
    Raises SctFetchError if no matching release is found.
    """
    candidates = [
        r for r in releases
        if _matches_cycle(r.get("tag_name", ""), cycle)
    ]
    if not candidates:
        prefix = _tag_prefix(cycle)
        raise SctFetchError(
            f"No GitHub release found for cycle {cycle.ident} "
            f"(expected tag starting with '{prefix}'). "
            "Check https://github.com/VATSIM-UK/uk-controller-pack/releases "
            "[RULE:SCT-RELEASE-TAG]"
        )
    # Sort by published_at (ISO 8601 strings sort correctly lexicographically)
    candidates.sort(key=lambda r: r.get("published_at", ""), reverse=True)
    return candidates[0]["tag_name"]


def _source_zip_url(tag: str) -> str:
    """Return the GitHub source zip URL for *tag*."""
    return _SOURCE_ZIP_URL.format(repo=_GITHUB_REPO, tag=tag)



def _extract_sct(zip_buffer: BytesIO, cycle: AiracCycle, dest_dir: Path) -> Path:
    """Extract the SCT file for *cycle* from *zip_buffer* into *dest_dir*.

    # [RULE:SCT-FILE-PATH]
    The file is located by finding a zip entry whose path contains the
    ``UK/data/`` component and whose basename matches ``UK_{YYYY}_{NN}.sct``.

    Extraction is atomic: the file is written to a temp directory first,
    then moved to *dest_dir* only on success.

    Returns the destination path.
    Raises SctFetchError if the file is not found.
    """
    target_basename = _sct_basename(cycle)
    final_path = dest_dir / target_basename

    tmp_dir = Path(tempfile.mkdtemp(dir=dest_dir, prefix=".sct_tmp_"))
    try:
        with zipfile.ZipFile(zip_buffer) as zf:
            for entry in zf.infolist():
                normalised = entry.filename.replace("\\", "/")
                if (
                    _SCT_DATA_DIR in normalised
                    and Path(normalised).name == target_basename
                ):
                    tmp_path = tmp_dir / target_basename
                    tmp_path.write_bytes(zf.read(entry.filename))
                    shutil.move(str(tmp_path), str(final_path))
                    return final_path

        raise SctFetchError(
            f"SCT file '{target_basename}' not found under '{_SCT_DATA_DIR}' "
            "in the source zip. The repo structure may have changed. "
            "[RULE:SCT-FILE-PATH]"
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_sct(
    cycle: AiracCycle,
    dest_dir: Path,
    *,
    releases_api_url: str = _RELEASES_API,
    timeout_api: int = 30,
    timeout_zip: int = 120,
) -> Path:
    """Download and extract the UK SCT sector file for *cycle*.

    Args:
        cycle:            The target AIRAC cycle.
        dest_dir:         Directory where the SCT file will be written.
                          Created if it does not already exist.
        releases_api_url: Override the GitHub releases API URL (for testing).
        timeout_api:      HTTP timeout for the releases API call.
        timeout_zip:      HTTP timeout for the source zip download.

    Returns:
        Path to the extracted SCT file.

    Raises:
        SctFetchError: on any network, structure, or missing-file failure.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 1. Fetch releases and find the latest tag for this cycle
    logger.info("Fetching GitHub releases: %s", releases_api_url)
    try:
        releases = _fetch_releases(releases_api_url, timeout=timeout_api)
    except urllib.error.HTTPError as exc:
        logger.error("HTTP %d fetching releases from %s", exc.code, releases_api_url)
        raise SctFetchError(
            f"HTTP {exc.code} fetching releases from {releases_api_url}"
        ) from exc
    except urllib.error.URLError as exc:
        logger.error("Network error fetching releases: %s", exc.reason)
        raise SctFetchError(
            f"Network error fetching releases: {exc.reason}"
        ) from exc
    logger.info("Received %d releases", len(releases))
    tag = _latest_tag_for_cycle(releases, cycle)
    logger.info("Selected tag: %s", tag)

    # 2. Download the source zip for that tag
    zip_url = _source_zip_url(tag)
    logger.info("Downloading source zip: %s", zip_url)
    try:
        zip_buffer = download_zip(zip_url, timeout=timeout_zip)
    except urllib.error.HTTPError as exc:
        logger.error("HTTP %d downloading source zip for tag '%s': %s", exc.code, tag, zip_url)
        raise SctFetchError(
            f"HTTP {exc.code} downloading source zip for tag '{tag}': {zip_url}"
        ) from exc
    except urllib.error.URLError as exc:
        logger.error("Network error downloading source zip: %s", exc.reason)
        raise SctFetchError(
            f"Network error downloading source zip: {exc.reason}"
        ) from exc
    logger.info("Source zip downloaded (%d bytes)", zip_buffer.getbuffer().nbytes)

    # 3. Extract the SCT file
    sct_path = _extract_sct(zip_buffer, cycle, dest_dir)
    logger.info("Extracted %s (%d bytes)", sct_path.name, sct_path.stat().st_size)
    return sct_path
