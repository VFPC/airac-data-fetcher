"""Shared HTTP zip downloader used by all source fetchers."""

from __future__ import annotations

import urllib.request
from io import BytesIO

_USER_AGENT = "airac-data-fetcher/1.0"


def download_zip(url: str, timeout: int = 120) -> BytesIO:
    """Download the zip at *url* into memory and return a BytesIO buffer.

    Args:
        url:     The URL of the zip file to download.
        timeout: HTTP timeout in seconds.

    Returns:
        An in-memory BytesIO buffer containing the zip data.

    Raises:
        urllib.error.HTTPError:  on a non-2xx HTTP response.
        urllib.error.URLError:   on a network-level failure.
    """
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return BytesIO(data)
