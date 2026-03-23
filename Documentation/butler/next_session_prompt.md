# AIRAC Data Fetcher — Next Session Prompt

_Last updated: 2026-03-23_

---

## Read First — Every Session

This repo is part of the vFPC ecosystem. Start every session at the hub:
`vFPC-Hub/Documentation/butler/next_session_prompt.md`

The ecosystem map is at `vFPC-Hub/Documentation/ecosystem.md`.

---

## Current State

**Branch:** `main` — all issues closed, no open work
**Tests:** 222 passing, 0 skipped
**Status:** Production-ready and in active use

---

## What This Tool Does

Downloads and prepares all input files for each AIRAC cycle:

1. Creates the cycle working directory (`vFPC YYNN/`)
2. Copies `in.json` forward from the previous cycle
3. Fetches eAIP ENR-3.2 and ENR-3.3 HTML (NATS AIP page)
4. Fetches and extracts the NATS SRD Excel file
5. Converts SRD Excel → `Routes.csv` + `Notes.csv`
6. Fetches the VATSIM UK sector file from uk-controller-pack releases
7. Writes a `fetcher_log_{timestamp}.txt` into the cycle directory

Run: `python -m src fetch --cycle YYNN`

Archiving is handled by the separate **airac-archiver** tool:
https://github.com/VFPC/airac-archiver

---

## Key Implementation Notes

- **Atomic extraction:** all fetchers extract to a temp dir, verify completeness, then
  move files into `dest_dir`. If any move fails, committed files are rolled back.
  `dest_dir` is always left in its original state on failure.
- **Logging:** `_setup_logging(work_dir)` in cli.py attaches a `FileHandler` to the
  `src` logger hierarchy. Clears existing handlers on repeated calls.
- **Rules DB:** `test_rules_db.py` finds `vFPC-Hub/Documentation/rules_reference.md`
  via sibling repo path. Set `VFPC_RULES_DB` env var to override.
- **config.local.yaml:** always required on each machine — set `workspace_base` at minimum.

---

## Rules

- `RULE:AIRAC-CYCLE-DAYS` — 28-day cycle (`src/airac.py`)
- `RULE:EAIP-PAGE-STRUCTURE` — NATS AIP heading/link format (`src/sources/eaip_html.py`)
- `RULE:SRD-DOWNLOAD-URL` — deterministic SRD zip URL (`src/sources/nats_srd.py`)
- `RULE:SRD-EXCEL-STRUCTURE` — sheet names, "What's New" header format (`src/processing/excel_to_csv.py`, `config.yaml`)
- `RULE:SCT-RELEASE-TAG` — GitHub release tag pattern (`src/sources/vatsim_sct.py`)
- `RULE:SCT-FILE-PATH` — SCT file location inside source zip (`src/sources/vatsim_sct.py`)

All 6 rules registered in `vFPC-Hub/Documentation/rules_reference.md` and verified
by `tests/test_rules_db.py`.

---

## If NATS Changes a URL or Structure

- **eAIP URL changes:** update `sources.eaip.page_url` in `config.yaml` and `_AIP_INDEX_URL` in `eaip_html.py`
- **SRD URL pattern changes:** update `_SRD_BASE` / `_srd_zip_url()` in `nats_srd.py` and the `RULE:SRD-DOWNLOAD-URL` comment
- **eAIP heading or link text changes:** update `_HEADING_PREFIX` / `_LINK_TEXT` in `eaip_html.py` and the `RULE:EAIP-PAGE-STRUCTURE` comment
- **SRD sheet names change:** update `config.yaml` and `_WHATS_NEW_SHEET` / `_ROUTES_SHEET` / `_NOTES_SHEET` in `excel_to_csv.py`

All changes require updating the corresponding `[RULE:...]` tag source and re-running
the rules DB tests.
