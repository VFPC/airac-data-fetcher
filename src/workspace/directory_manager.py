"""Manage per-AIRAC-cycle directory structure and in.json copy-forward."""

from __future__ import annotations

import shutil
from datetime import timedelta
from pathlib import Path

from src.airac import AiracCycle, cycle_for_date

_IN_JSON = "in.json"
_DIR_PREFIX = "vFPC "


def cycle_dir(workspace_base: Path, cycle: AiracCycle) -> Path:
    """Return the path for *cycle*'s working directory.

    The directory is named ``vFPC {ident}`` (e.g. ``vFPC 2602``) to match
    the production naming convention. This function does not create it.
    """
    return workspace_base / f"{_DIR_PREFIX}{cycle.ident}"


def ensure_cycle_dir(workspace_base: Path, cycle: AiracCycle) -> Path:
    """Create *cycle*'s working directory if it doesn't already exist.

    Safe to call multiple times (idempotent). Returns the directory path.
    """
    path = cycle_dir(workspace_base, cycle)
    path.mkdir(parents=True, exist_ok=True)
    return path


def copy_in_json_forward(workspace_base: Path, cycle: AiracCycle) -> Path | None:
    """Copy ``in.json`` from the previous cycle's directory into *cycle*'s directory.

    The copy is skipped — returning ``None`` — when any of the following apply:

    - *cycle*'s directory already contains ``in.json`` (never overwrite)
    - the previous cycle directory does not exist
    - the previous cycle directory contains no ``in.json``

    When a copy is made the destination path is returned.  The destination
    directory is created if it does not yet exist.
    """
    dest_dir = cycle_dir(workspace_base, cycle)
    dest = dest_dir / _IN_JSON

    if dest.exists():
        return None

    prev_cycle = cycle_for_date(cycle.effective_date - timedelta(days=1))
    src = cycle_dir(workspace_base, prev_cycle) / _IN_JSON

    if not src.exists():
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest
