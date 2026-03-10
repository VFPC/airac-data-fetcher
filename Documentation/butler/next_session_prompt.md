# AIRAC Data Fetcher — Next Session Prompt

_Last updated: 2026-03-10 (Session 7 — Excel→CSV converter; archiver questions pending)_

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
- **Status:** In progress — all fetchers + Excel→CSV complete; archiver and CLI next
- **Tests:** 180 (all passing)
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

---

## Next Steps

1. **Design and implement `src/archive/archiver.py`** — the following questions were raised at end of session and must be answered before coding begins:

   **What files go in the zip?**
   - Working directory `vFPC YYNN/` will contain: `Routes.csv`, `Notes.csv`, `EG-ENR-3.2-en-GB.html`, `EG-ENR-3.3-en-GB.html`, `UK_YYYY_NN.sct`, `in.json`, and the raw SRD `.xlsx`.
   - Does everything go in, or only a subset? Does the raw Excel go in or just the CSVs?

   **Structure in airac-data repo?**
   - Option A: flat — `vFPC 2602.zip` + `vFPC 2602_manifest.md` in the repo root
   - Option B: subdirectory — `vFPC 2602/` containing the zip and manifest inside it
   - Which layout matches what you expect?

   **What goes in the manifest?**
   - Proposed: cycle ident, effective/expiry dates, list of files with sizes and checksums (SHA-256), timestamp of archive creation, source URL/tag each file came from.
   - Is that right, or simpler?

   **Git interaction?**
   - Rule is "does not auto-commit — user reviews first."
   - Option A: archiver writes zip + manifest, stops there — no git at all.
   - Option B: archiver writes files then runs `git add` so files are staged and ready for your review/commit.
   - Which do you prefer?

2. **Implement `src/cli.py`** — Click entry point tying all fetchers, converter, and archiver together for a given cycle.

---

## Critical Rules

1. **config.yaml** stores all URLs and patterns — never hardcode download URLs in Python source.
2. **config.local.yaml** is gitignored — use it for user-specific path overrides.
3. **Main branch stays minimal** — all implementation work on `first-try` until ready to merge.
4. **The archive step does not auto-commit** — it stages files in the airac-data repo for the user to review before committing.
5. **in.json is never modified** — only copied forward from the previous cycle if the new directory doesn't already exist.
