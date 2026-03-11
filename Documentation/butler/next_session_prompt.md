# AIRAC Data Fetcher — Next Session Prompt

_Last updated: 2026-03-11 (Session 10 — Archiver extracted to airac-archiver repo)_

---

## Context

This is a Python CLI tool to automate the download, extraction, and preparation of all input files needed by the [SRD Parser](https://github.com/VFPC/New-SRDParser) and [AIP Parser](https://github.com/VFPC/AIP-Parser) for each AIRAC cycle. It replaces the manual steps in the AIRAC maintenance checklist (VFPC/New-SRDParser#12).

A companion repo, [VFPC/airac-data](https://github.com/VFPC/airac-data), provides long-term zip-based archival of input files per cycle.

### Relationship to other repos

| Repo | Relationship |
|------|-------------|
| VFPC/New-SRDParser | Consumer — reads CSV, SCT, in.json prepared by this tool |
| VFPC/AIP-Parser | Consumer — reads ENR 3.2/3.3 HTML prepared by this tool |
| VFPC/airac-data | Archive — receives zipped input files from this tool |
| VFPC/vFPC-Rules-Database | No direct relationship |

---

## Current State

- **Branch:** `first-try`
- **Status:** Feature-complete, code-reviewed, and documented — waiting on live AIRAC data
- **Tests:** 204 (all passing)
- **Dependencies:** requests, beautifulsoup4, openpyxl, pyyaml, click, pytest

---

## What Was Completed

### Session 1 (2026-03-10) — Scaffolding
- Repos created: `VFPC/airac-data-fetcher` and `VFPC/airac-data`
- Main branch has README and .gitignore only
- `first-try` branch has full project structure scaffolded
- Butler documentation seeded; `config.yaml` template created

### Session 2 (2026-03-10) — AIRAC cycle calculator
- `src/airac.py` fully implemented: `AiracCycle` dataclass, `cycle_for_date`, `current_cycle`
- `tests/test_airac.py`: 29 tests; `RULE:AIRAC-CYCLE-DAYS` tagged (new `AIRAC-` prefix in rules DB)
- Anchor: `2024-01-25 = AIRAC 2401`

### Session 3 (2026-03-10) — Config loader + directory manager
- `src/config.py`: `load()`, deep-merge of `config.local.yaml`, frozen dataclasses, `ConfigError`; 22 tests
- `src/workspace/directory_manager.py`: `cycle_dir()`, `ensure_cycle_dir()`, `copy_in_json_forward()`; 19 tests
- Production naming confirmed: `vFPC YYNN` (e.g. `vFPC 2602`), previous cycle lookup via `cycle_for_date(effective - 1 day)`
- Cross-repo context loaded: Rules Database convention + AIP Parser data dictionary

### Session 4 (2026-03-10) — eAIP HTML fetcher
- `src/sources/eaip_html.py`: full pipeline (index page scrape → zip download → extract → validate); 25 tests
- `RULE:EAIP-PAGE-STRUCTURE` registered in rules DB (new `EAIP-` domain prefix)
- Heading format `"AIRAC NN/YYYY"` and link text `"Offline HTML Download"` are tagged; mismatch raises `EaipFetchError` with rule citation
- AIP Parser integration: fetcher writes `EG-ENR-3.2-en-GB.html` and `EG-ENR-3.3-en-GB.html` into the cycle directory; AIP Parser reads from there when wired to production

### Session 5 (2026-03-10) — NATS SRD fetcher
- `src/sources/nats_srd.py`: direct URL construction (no page scraping) → zip download → Excel extraction; 22 tests
- `RULE:SRD-DOWNLOAD-URL` registered in rules DB (new `SRD-` domain prefix)
- URL pattern `AIRAC-{NN}-{YYYY}.zip` confirmed from live page showing both current and next cycle links
- Excel extracted by extension only — filename is descriptive and changes each cycle

### Session 6 (2026-03-10) — VATSIM SCT fetcher
- `src/sources/vatsim_sct.py`: GitHub releases API → latest patch tag → source zip download → SCT extraction; 35 tests
- `RULE:SCT-RELEASE-TAG`, `RULE:SCT-FILE-PATH` registered (new `SCT-` domain prefix)

### Session 7 (2026-03-10) — Excel→CSV converter
- `src/processing/excel_to_csv.py`: "What's New" date validation → Routes.csv + Notes.csv export; 28 tests
- `RULE:SRD-EXCEL-STRUCTURE` registered; config `sheet_name` default corrected from `"SRD"` → `"Routes"`
- Validation fires before any file is written — wrong-cycle download fails loudly and cleanly

### Session 8 (2026-03-11) — Archiver (now in airac-archiver)
- Originally implemented here as `src/archive/archiver.py`; moved in Session 10
- See https://github.com/VFPC/airac-archiver for the standalone archiver tool

### Session 9 (2026-03-11) — CLI
- `src/cli.py`: Click group with `fetch` subcommand; 25 tests
- `src/__main__.py`: module entry point (run via `python -m src`)
- `fetch --cycle YYNN` — runs all 6 steps in order; defaults to current cycle
- All domain errors caught and printed cleanly (no tracebacks); non-zero exit on any failure
- eAIP `page_url` from config passed through if set, otherwise fetcher default used

### Session 10 (2026-03-11) — Archiver extraction
- `src/archive/archiver.py` and its tests removed from this repo
- `archive_repo` removed from `src/config.py` and `config.yaml` (not needed by fetcher)
- `archive` CLI subcommand removed; fetch output now references airac-archiver
- New standalone repo: https://github.com/VFPC/airac-archiver (108 tests, all green)

---

## Next Steps

All remaining work is blocked on live AIRAC data being available for the March cycle. GitHub issues have been created:

1. **Issue #1** — Live end-to-end test: run `python -m src fetch --cycle 2603` against real NATS and GitHub sources
2. **Issue #2** — Populate `config.yaml` source URLs once confirmed from the live test
3. **Issue #3** — Merge `first-try` → `main` (requires #1 and #2 closed first; README update needed before merge)

Start with **issue #1** when the March data is available. Close #2 as part of that run, then #3.

---

## Critical Rules

1. **config.yaml** stores all URLs and patterns — never hardcode download URLs in Python source.
2. **config.local.yaml** is gitignored — use it for user-specific path overrides.
3. **Main branch stays minimal** — all implementation work on `first-try` until ready to merge.
4. **Archiving is handled by airac-archiver** — a separate repo; does not auto-commit.
5. **in.json is never modified** — only copied forward from the previous cycle if the new directory doesn't already exist.
