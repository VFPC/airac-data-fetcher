"""CLI entry point for the AIRAC Data Fetcher.

Usage
-----
Run via the module entry point::

    python -m src.cli fetch [--cycle YYNN]
    python -m src.cli archive [--cycle YYNN]

Commands
--------
fetch
    Download all source files for a cycle and convert the SRD Excel to CSV.
    Steps run in order:

    1. Create the cycle working directory under workspace_base.
    2. Copy in.json forward from the previous cycle (skipped if already present).
    3. Fetch eAIP ENR-3.2 and ENR-3.3 HTML files from the NATS AIP page.
    4. Fetch the SRD Excel zip from NATS and extract the .xlsx file.
    5. Validate and convert the SRD Excel to Routes.csv and Notes.csv.
    6. Fetch the VATSIM UK sector file (.sct) from the uk-controller-pack release.

archive
    Zip the prepared cycle files and stage them in the airac-data repo.
    Requires that the SRD Parser has been run (out.json must be present).

    Steps run in order:

    1. Collect all seven required files from the cycle working directory.
    2. Create the zip and manifest in the archive repo subdirectory.
    3. Run git add to stage both files for user review before committing.
"""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import click

from src.airac import AiracCycle, current_cycle, cycle_for_date
from src.archive.archiver import ArchiverError, archive_cycle
from src.config import ConfigError, load
from src.processing.excel_to_csv import ExcelValidationError, convert_srd_excel
from src.sources.eaip_html import EaipFetchError, fetch_eaip_html
from src.sources.nats_srd import SrdFetchError, fetch_srd
from src.sources.vatsim_sct import SctFetchError, fetch_sct
from src.workspace.directory_manager import (
    copy_in_json_forward,
    cycle_dir,
    ensure_cycle_dir,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IDENT_RE = re.compile(r"^\d{4}$")


def _resolve_cycle(ident: str | None) -> AiracCycle:
    """Return the AiracCycle for *ident* (YYNN), or the current cycle if None."""
    if ident is None:
        return current_cycle()

    if not _IDENT_RE.match(ident):
        raise click.BadParameter(
            f"'{ident}' is not a valid cycle ident — expected 4 digits, e.g. '2603'.",
            param_hint="'--cycle'",
        )

    year = 2000 + int(ident[:2])
    number = int(ident[2:])

    if number < 1 or number > 13:
        raise click.BadParameter(
            f"Cycle number {number} is out of range (1–13).",
            param_hint="'--cycle'",
        )

    # Walk from cycle 1 of that year to the target cycle number
    c = cycle_for_date(date(year, 1, 1))
    if c.year < year:
        c = c.next
    target = cycle_for_date(c.effective_date + timedelta(days=(number - 1) * 28))

    if target.ident != ident:
        raise click.BadParameter(
            f"Could not resolve cycle ident '{ident}'. "
            "Check that the year and number are correct.",
            param_hint="'--cycle'",
        )
    return target


def _step(n: int, total: int, description: str) -> None:
    click.echo(f"  [{n}/{total}] {description}...", nl=False)


def _ok(detail: str = "") -> None:
    suffix = f"  ({detail})" if detail else ""
    click.echo(f" done{suffix}")


def _abort(message: str) -> None:
    click.echo(f"\nError: {message}", err=True)
    sys.exit(1)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def cli() -> None:
    """AIRAC Data Fetcher — download and prepare files for the SRD and AIP parsers."""


# ---------------------------------------------------------------------------
# fetch command
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--cycle", "-c",
    default=None,
    metavar="YYNN",
    help="AIRAC cycle ident to fetch (e.g. 2603). Defaults to the current cycle.",
)
def fetch(cycle: str | None) -> None:
    """Download all source files for a cycle and convert the SRD Excel to CSV."""
    try:
        cfg = load()
    except ConfigError as exc:
        _abort(str(exc))

    try:
        target = _resolve_cycle(cycle)
    except click.BadParameter as exc:
        _abort(str(exc))

    work_dir = cycle_dir(cfg.workspace_base, target)

    click.echo(f"\nCycle:     {target}")
    click.echo(f"Directory: {work_dir}\n")

    total = 6

    # Step 1 — working directory
    _step(1, total, "Creating working directory")
    ensure_cycle_dir(cfg.workspace_base, target)
    _ok()

    # Step 2 — in.json copy-forward
    _step(2, total, "Copying in.json from previous cycle")
    result = copy_in_json_forward(cfg.workspace_base, target)
    if result:
        _ok(f"copied from previous cycle")
    else:
        click.echo(" skipped (already present or no previous cycle found)")

    # Step 3 — eAIP HTML
    _step(3, total, "Fetching eAIP HTML (ENR-3.2 and ENR-3.3)")
    try:
        kwargs: dict = {}
        if cfg.sources.eaip.page_url:
            kwargs["index_url"] = cfg.sources.eaip.page_url
        eaip_files = fetch_eaip_html(target, work_dir, **kwargs)
        _ok(", ".join(eaip_files.keys()))
    except EaipFetchError as exc:
        _abort(str(exc))

    # Step 4 — SRD Excel download
    _step(4, total, "Fetching SRD Excel")
    try:
        srd_files = fetch_srd(target, work_dir)
        excel_path = next(iter(srd_files.values()))
        _ok(excel_path.name)
    except SrdFetchError as exc:
        _abort(str(exc))

    # Step 5 — Excel → CSV conversion
    _step(5, total, "Converting SRD Excel to CSV")
    try:
        csv_files = convert_srd_excel(excel_path, work_dir, target)
        _ok(", ".join(p.name for p in csv_files.values()))
    except ExcelValidationError as exc:
        _abort(str(exc))

    # Step 6 — VATSIM SCT
    _step(6, total, "Fetching VATSIM UK sector file")
    try:
        sct_path = fetch_sct(target, work_dir)
        _ok(sct_path.name)
    except SctFetchError as exc:
        _abort(str(exc))

    click.echo(f"\nAll files ready in: {work_dir}")
    click.echo("Run the SRD Parser, then use 'archive' when out.json is written.")


# ---------------------------------------------------------------------------
# archive command
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--cycle", "-c",
    default=None,
    metavar="YYNN",
    help="AIRAC cycle ident to archive (e.g. 2603). Defaults to the current cycle.",
)
def archive(cycle: str | None) -> None:
    """Zip the prepared cycle files and stage them in the airac-data repo."""
    try:
        cfg = load()
    except ConfigError as exc:
        _abort(str(exc))

    try:
        target = _resolve_cycle(cycle)
    except click.BadParameter as exc:
        _abort(str(exc))

    work_dir = cycle_dir(cfg.workspace_base, target)

    click.echo(f"\nCycle:       {target}")
    click.echo(f"Working dir: {work_dir}")
    click.echo(f"Archive repo: {cfg.archive_repo}\n")

    click.echo("  Collecting files, creating zip, writing manifest, staging...", nl=False)
    try:
        zip_path, manifest_path = archive_cycle(target, work_dir, cfg.archive_repo)
    except ArchiverError as exc:
        click.echo("")  # end the partial line before printing the error
        _abort(str(exc))

    click.echo(" done")
    click.echo(f"\nStaged for review:")
    click.echo(f"  {zip_path}")
    click.echo(f"  {manifest_path}")
    click.echo("\nReview and commit when ready.")


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
