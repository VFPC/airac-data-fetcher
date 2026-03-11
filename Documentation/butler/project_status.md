# AIRAC Data Fetcher — Project Status

## Current Project State (2026-03-11, Session 9)

### System Status: FEATURE-COMPLETE

**Branch:** `first-try`
**Tests:** 263 (all passing)
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

- **`src/archive/archiver.py`** — fully implemented, tested (45 tests)
  - Collects all 7 required files: Routes.csv, Notes.csv, EG-ENR-3.2-en-GB.html, EG-ENR-3.3-en-GB.html, UK_YYYY_NN.sct, in.json, out.json
  - Creates `{archive_repo}/vFPC YYNN/vFPC YYNN.zip` (flat layout, ZIP_DEFLATED)
  - Writes `manifest.md` with cycle dates, UTC timestamp, and OS username
  - Runs `git add` to stage both files for user review; never auto-commits

- **`src/cli.py`** — fully implemented, tested (38 tests)
  - `fetch [--cycle YYNN]` — creates dir, copies in.json forward, fetches eAIP/SRD/SCT, converts Excel→CSV
  - `archive [--cycle YYNN]` — zips files and stages in airac-data repo
  - All domain errors caught cleanly; non-zero exit on failure
  - Run via `python -m src fetch` / `python -m src archive`

### What Needs Work

- Live end-to-end test against real NATS/GitHub sources
- Populate `page_url` placeholders in `config.yaml` once confirmed
- Merge `first-try` → `main` after live test passes
- Optional: add `pyproject.toml` with `[project.scripts]` entry point

---

Last Updated: 2026-03-11
Status: Feature-complete — all modules implemented and tested; live end-to-end test pending
