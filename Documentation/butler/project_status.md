# AIRAC Data Fetcher — Project Status

## Current Project State (2026-03-10, Session 1)

### System Status: SCAFFOLDED

The project structure is in place but no implementation has been written yet.

**Branch:** `first-try`
**Tests:** 0
**Dependencies:** requests, beautifulsoup4, openpyxl, pyyaml, click, pytest

### What Exists

- Project directory structure (`src/`, `tests/`, `Documentation/butler/`)
- `config.yaml` template with placeholder URLs
- `requirements.txt` with all planned dependencies
- `.gitignore` for Python projects
- Butler documentation (this file, next_session_prompt, session_status_summary)

### What Needs Work

See GitHub Issues for all open work: https://github.com/VFPC/airac-data-fetcher/issues

Key implementation areas:
- AIRAC cycle calculator (date math)
- Source fetchers (NATS SRD, VATSIM SCT, UK eAIP)
- Excel to CSV conversion
- Directory manager (cycle dirs, in.json copy-forward)
- Archiver (zip + manifest for airac-data repo)
- CLI entry point

---

Last Updated: 2026-03-10
Status: Scaffolded — no implementation yet
Next steps: see https://github.com/VFPC/airac-data-fetcher/issues
