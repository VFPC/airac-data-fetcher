# AIRAC Data Fetcher — Project Status

## Current Project State (2026-03-11, Session 10)

### System Status: FEATURE-COMPLETE

**Branch:** `first-try`
**Tests:** 204 (all passing)
**Dependencies:** requests, beautifulsoup4, openpyxl, pyyaml, click, pytest

### What Exists

- Project directory structure (`src/`, `tests/`, `Documentation/butler/`)
- `config.yaml` template with placeholder URLs
- `requirements.txt` with all planned dependencies
- `.gitignore` for Python projects
- Butler documentation (this file, next_session_prompt, session_status_summary)
- **`src/airac.py`** — fully implemented, tested (29 tests)
- **`src/config.py`** — fully implemented, tested (22 tests)
- **`src/workspace/directory_manager.py`** — fully implemented, tested (19 tests)
- **`src/sources/eaip_html.py`** — fully implemented, tested (25 tests)
  - Scrapes NATS AIP page for cycle download link (`RULE:EAIP-PAGE-STRUCTURE`)
  - Downloads zip, extracts ENR-3.2 and ENR-3.3 by basename
  - Validates `EM.effectiveDateStart` meta tag against cycle effective date
- **`src/sources/nats_srd.py`** — fully implemented, tested (22 tests)
  - URL constructed directly from cycle: `AIRAC-{NN}-{YYYY}.zip` (`RULE:SRD-DOWNLOAD-URL`)
  - Downloads zip, extracts Excel file(s) by extension
  - HTTP/network errors wrapped as `SrdFetchError` with rule citation
- **`src/sources/vatsim_sct.py`** — fully implemented, tested (35 tests)
  - Queries GitHub releases API for VATSIM-UK/uk-controller-pack (`RULE:SCT-RELEASE-TAG`)
  - Picks most recently published release matching `{YYYY}_{NN}[a-z]*`
  - Downloads source zip; extracts `UK_{YYYY}_{NN}.sct` from `UK/data/` (`RULE:SCT-FILE-PATH`)

- **`src/processing/excel_to_csv.py`** — fully implemented, tested (28 tests)
  - Scans "What's New" sheet for `"What's New - {D}{ord} {Month} {YYYY} AIRAC"` header (`RULE:SRD-EXCEL-STRUCTURE`)
  - Validates embedded date against `cycle.effective_date` — catches wrong-cycle downloads with operator-readable error
  - Exports "Routes" → `Routes.csv` (SRD Parser input) and "Notes" → `Notes.csv`

- **`src/cli.py`** — fully implemented, tested (25 tests)
  - `fetch [--cycle YYNN]` — creates dir, copies in.json forward, fetches eAIP/SRD/SCT, converts Excel→CSV
  - All domain errors caught cleanly; non-zero exit on failure
  - Run via `python -m src fetch`
  - Archive step handled by the separate **airac-archiver** tool: https://github.com/VFPC/airac-archiver

### What Needs Work

- Live end-to-end test against real NATS/GitHub sources
- Populate `page_url` placeholders in `config.yaml` once confirmed
- Merge `first-try` → `main` after live test passes
- Optional: add `pyproject.toml` with `[project.scripts]` entry point

### Archiver moved

The archiver (`src/archive/archiver.py`) was extracted to its own repository
in Session 10: **https://github.com/VFPC/airac-archiver**
Run `airac-archiver` after the SRD Parser to package and stage cycle data.

---

Last Updated: 2026-03-11
Status: Feature-complete — all modules implemented and tested; live end-to-end test pending
