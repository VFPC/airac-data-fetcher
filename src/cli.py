"""CLI entry point for the AIRAC Data Fetcher.

Usage
-----
Run via the module entry point::

    python -m src fetch [--cycle YYNN]

Commands
--------
fetch
    Download all source files for a cycle and convert the SRD Excel to CSV.
    Steps run in order:

    1. Create the cycle working directory under workspace_base.
    2. Copy in.json forward from the previous cycle (skipped if already present).
    3. Fetch eAIP ENR-2.1, ENR-2.2, ENR-3.2, ENR-3.3, ENR-4.1, ENR-4.2, ENR-4.4 HTML files from the NATS AIP page.
    4. Fetch the SRD Excel zip from NATS and extract the .xlsx file.
    5. Validate and convert the SRD Excel to Routes.csv and Notes.csv.
    6. Fetch the VATSIM UK sector file (.sct) from the uk-controller-pack release.
    7. Fetch EI_ENR_4_4_EN.pdf from the AirNav Ireland IAIP package page (non-fatal).

After fetching, run the SRD Parser to produce out.json, then use the
airac-archiver tool to package and stage the files: https://github.com/VFPC/airac-archiver
"""

from __future__ import annotations

import logging
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import click

from src.airac import AiracCycle, current_cycle, cycle_for_date
from src.config import ConfigError, load
from src.processing.excel_to_csv import ExcelValidationError, convert_srd_excel
from src.sources.eaip_html import EaipFetchError, fetch_eaip_html
from src.sources.irish_eaip_pdf import fetch_irish_enr44
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


_LOG_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _setup_logging(log_dir: Path) -> Path:
    """Configure logging to a timestamped file in *log_dir*.

    Returns the log file path.  The ``src`` logger hierarchy is set to INFO;
    all messages flow to a single file handler.

    Any existing file handlers on the ``src`` logger are closed and removed
    first so that repeated calls (e.g. two ``fetch`` invocations in the same
    process) do not accumulate handlers or duplicate log lines.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"fetcher_log_{timestamp}.txt"

    src_logger = logging.getLogger("src")
    for existing in src_logger.handlers[:]:
        existing.close()
        src_logger.removeHandler(existing)

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT))

    src_logger.setLevel(logging.INFO)
    src_logger.addHandler(handler)

    return log_path


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

    total = 7

    # Step 1 — working directory
    _step(1, total, "Creating working directory")
    ensure_cycle_dir(cfg.workspace_base, target)
    _ok()

    # Set up file logging into the cycle directory
    log_path = _setup_logging(work_dir)
    cli_logger = logging.getLogger("src.cli")
    cli_logger.info("=== airac-data-fetcher run started ===")
    cli_logger.info("Cycle: %s", target)
    cli_logger.info("Directory: %s", work_dir)

    # Step 2 — in.json copy-forward
    _step(2, total, "Copying in.json from previous cycle")
    result = copy_in_json_forward(cfg.workspace_base, target)
    if result:
        _ok(f"copied from previous cycle")
        cli_logger.info("in.json copied forward from previous cycle to %s", result)
    else:
        click.echo(" skipped (already present or no previous cycle found)")
        cli_logger.info("in.json copy-forward skipped (already present or no previous cycle)")

    # Step 3 — eAIP HTML
    _step(3, total, "Fetching eAIP HTML (ENR-2.1, ENR-2.2, ENR-3.2, ENR-3.3, ENR-4.1, ENR-4.2, ENR-4.4)")
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

    # Step 7 — Irish ENR 4.4 PDF (non-fatal: warns and continues if unavailable)
    _step(7, total, "Fetching Irish eAIP ENR 4.4 PDF (EI_ENR_4_4_EN.pdf)")
    kwargs_ie: dict = {}
    if cfg.sources.irish_eaip.page_url:
        kwargs_ie["page_url"] = cfg.sources.irish_eaip.page_url
    ie_path = fetch_irish_enr44(work_dir, **kwargs_ie)
    if ie_path:
        _ok(ie_path.name)
        cli_logger.info("EI_ENR_4_4_EN.pdf written to %s", ie_path)
    else:
        click.echo(" skipped (unavailable — see log for details)")
        cli_logger.warning("EI_ENR_4_4_EN.pdf fetch skipped — check log for details")

    cli_logger.info("=== All files ready — run complete ===")

    click.echo(f"\nAll files ready in: {work_dir}")
    click.echo(f"Log file: {log_path}")
    click.echo("Run the SRD Parser, then use airac-archiver when out.json is written.")
    click.echo("  https://github.com/VFPC/airac-archiver")


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
