# AIRAC Data Fetcher — Project Status

_Last updated: 2026-03-23_

---

## System Status: PRODUCTION-READY

**Branch:** `main`
**Tests:** 222 (all passing, 0 skipped)
**Dependencies:** beautifulsoup4, openpyxl, pyyaml, click, pytest

---

## Module Inventory

| Module | Tests | Notes |
|--------|-------|-------|
| `src/airac.py` | 29 | AIRAC cycle date arithmetic; anchor 2024-01-25 = 2401 |
| `src/config.py` | 22 | YAML loader with `config.local.yaml` deep-merge |
| `src/workspace/directory_manager.py` | 19 | Cycle dir creation; `in.json` copy-forward |
| `src/sources/eaip_html.py` | 31 | NATS AIP scrape → zip → extract → date validate |
| `src/sources/nats_srd.py` | 27 | Deterministic SRD zip URL → Excel extract |
| `src/sources/vatsim_sct.py` | 38 | GitHub releases API → source zip → SCT extract |
| `src/processing/excel_to_csv.py` | 28 | "What's New" date validate → Routes.csv + Notes.csv |
| `src/processing/zip_handler.py` | — | Shared HTTP downloader (covered by source tests) |
| `src/cli.py` | 27 | Click `fetch` command; file logging to cycle dir |
| `tests/test_rules_db.py` | 2 | Rules DB bidirectional tag check (requires vFPC-Hub sibling) |

---

## Key Properties

- **Atomic extraction:** all three fetchers extract to a temp dir, verify completeness,
  then move files into `dest_dir`. On any failure (missing file or move error) already-moved
  files are rolled back and the temp dir is cleaned up. `dest_dir` is always left unchanged.
- **Run logging:** each `fetch` invocation writes `fetcher_log_{timestamp}.txt` into the
  cycle working directory alongside the data files. Existing file handlers are cleared on
  repeated calls — no handler accumulation.
- **Rules DB coverage:** `test_rules_db.py` verifies bidirectional tag consistency against
  `vFPC-Hub/Documentation/rules_reference.md`. Requires `vFPC-Hub` to be a sibling repo
  (or `VFPC_RULES_DB` env var set). All 6 registered tags verified.

---

## Config

`config.yaml` is committed with confirmed live source URLs (verified 2026-03-20, issue #1):

| Field | Value |
|-------|-------|
| `sources.eaip.page_url` | `https://nats-uk.ead-it.com/cms-nats/opencms/en/Publications/AIP/` |
| `sources.nats_srd.page_url` | `https://nats-uk.ead-it.com/cms-nats/opencms/en/Publications/digital-datasets/SRD/` (informational only) |

Machine-specific paths go in `config.local.yaml` (gitignored). Minimum required:

```yaml
workspace_base: "C:\\path\\to\\your\\vFPC files"
```

---

## GitHub Issues — All Closed

| # | Title | Closed |
|---|-------|--------|
| #1 | Live end-to-end test | 2026-03-20 |
| #2 | Populate config.yaml source URLs | 2026-03-23 |
| #3 | Merge first-try to main | 2026-03-20 (PR #7) |
| #5 | Non-atomic extraction leaves partial files | 2026-03-23 |
| #6 | Add run logging to cycle directory | 2026-03-23 |

No open issues.

---

## Archiver

The archiver is a separate tool: **https://github.com/VFPC/airac-archiver**

After `fetch` completes and the SRD Parser has written `out.json`, run airac-archiver
to package and stage the cycle files in `VFPC/airac-data`.
