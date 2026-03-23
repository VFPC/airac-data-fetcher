"""Validate that [RULE:...] tags in source code are registered in rules_reference.md.

This test implements the contract defined in the vFPC Rules Database convention:
  https://github.com/VFPC/vFPC-Rules-Database/blob/main/Documentation/convention.md

The test:
  1. Locates rules_reference.md via the VFPC_RULES_DB environment variable or
     by walking up from this file to find the sibling vFPC-Rules-Database repo.
     Skips gracefully if neither is found (e.g. on CI without the full repo tree).
  2. Parses every [RULE:...] tag from rules_reference.md.
  3. Scans all .py source files in src/ for [RULE:...] occurrences.
  4. Asserts:
     - Every tag found in source also appears in the document.
     - Every tag in the document that lists this repo also appears in source.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Locating the rules database
# ---------------------------------------------------------------------------

# Matches [RULE:...] in source code and `RULE:...` in the Markdown table
_TAG_RE = re.compile(r"(?:\[|`)RULE:([A-Z0-9][A-Z0-9\-]*)(?:\]|`)")
_REPO_ROOT = Path(__file__).parent.parent
_SRC_DIR = _REPO_ROOT / "src"

# Column header as it appears in rules_reference.md
_FETCHER_COLUMN = "airac-data-fetcher Files"


def _find_rules_db() -> Path | None:
    """Return the path to rules_reference.md, or None if not available."""
    env_path = os.environ.get("VFPC_RULES_DB")
    if env_path:
        p = Path(env_path)
        return p if p.exists() else None

    # The rules database lives in vFPC-Hub (the project hub repo), which is
    # a sibling of this repo.  Legacy name vFPC-Rules-Database is also checked
    # so that CI environments with the old layout still work.
    for sibling in ("vFPC-Hub", "vFPC-Rules-Database"):
        candidate = _REPO_ROOT.parent / sibling / "Documentation" / "rules_reference.md"
        if candidate.exists():
            return candidate
    return None


def _extract_tags(text: str) -> set[str]:
    """Return all RULE:... tag identifiers found in *text*.

    Matches both ``[RULE:NAME]`` (source code style) and `` `RULE:NAME` ``
    (Markdown table style), returning just the NAME part normalised with
    ``[RULE:NAME]`` wrapper so comparisons are consistent.
    """
    return {f"[RULE:{m}]" for m in _TAG_RE.findall(text)}


def _tags_in_source() -> set[str]:
    """Return all [RULE:...] tags found in .py files under src/."""
    tags: set[str] = set()
    for py_file in _SRC_DIR.rglob("*.py"):
        tags |= _extract_tags(py_file.read_text(encoding="utf-8"))
    return tags


def _tags_in_rules_db(rules_path: Path) -> set[str]:
    """Return all [RULE:...] tags found in rules_reference.md."""
    return _extract_tags(rules_path.read_text(encoding="utf-8"))


def _tags_attributed_to_fetcher(rules_path: Path) -> set[str]:
    """Return tags whose airac-data-fetcher Files column is non-empty.

    Parses the Markdown table row by row, checking whether the column
    corresponding to _FETCHER_COLUMN has a non-empty, non-dash value.
    """
    text = rules_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Find the header row and locate the fetcher column index
    header_idx = None
    col_idx = None
    for i, line in enumerate(lines):
        if _FETCHER_COLUMN in line and "|" in line:
            header_idx = i
            cols = [c.strip() for c in line.split("|")]
            try:
                col_idx = cols.index(_FETCHER_COLUMN)
            except ValueError:
                return set()
            break

    if header_idx is None or col_idx is None:
        return set()

    attributed: set[str] = set()
    for line in lines[header_idx + 2:]:  # skip header and separator row
        if not line.strip().startswith("|"):
            break
        cells = [c.strip() for c in line.split("|")]
        if len(cells) <= col_idx:
            continue
        tag_cell = cells[1] if len(cells) > 1 else ""
        fetcher_cell = cells[col_idx] if len(cells) > col_idx else ""
        tags = _extract_tags(tag_cell)
        if tags and fetcher_cell and fetcher_cell not in ("", "—", "-"):
            attributed |= tags

    return attributed


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rules_db_path() -> Path:
    """Return rules_reference.md path, or skip the test module if not found."""
    path = _find_rules_db()
    if path is None:
        pytest.skip(
            "rules_reference.md not found. "
            "Set VFPC_RULES_DB env var or ensure vFPC-Rules-Database is a sibling repo."
        )
    return path


class TestRulesDatabase:
    def test_all_source_tags_are_registered(self, rules_db_path):
        """Every [RULE:...] tag used in src/ must appear in rules_reference.md."""
        source_tags = _tags_in_source()
        db_tags = _tags_in_rules_db(rules_db_path)
        unregistered = source_tags - db_tags
        assert not unregistered, (
            f"The following tags are used in source but not registered in "
            f"rules_reference.md:\n"
            + "\n".join(f"  {t}" for t in sorted(unregistered))
        )

    def test_attributed_fetcher_tags_exist_in_source(self, rules_db_path):
        """Every tag attributed to airac-data-fetcher in the DB must appear in src/."""
        source_tags = _tags_in_source()
        attributed = _tags_attributed_to_fetcher(rules_db_path)
        stale = attributed - source_tags
        assert not stale, (
            f"The following tags are listed under '{_FETCHER_COLUMN}' in "
            f"rules_reference.md but were not found in src/:\n"
            + "\n".join(f"  {t}" for t in sorted(stale))
        )
