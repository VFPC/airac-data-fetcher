# AIRAC Data Fetcher — Next Session Prompt

_Generated: 2026-03-10 (Session 1 — repo scaffolding)_

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
- **Status:** Scaffolded — no implementation yet
- **Tests:** 0
- **Dependencies:** requests, beautifulsoup4, openpyxl, pyyaml, click, pytest

---

## What Was Completed in Session 1 (2026-03-10)

- Repos created: `VFPC/airac-data-fetcher` and `VFPC/airac-data`
- Main branch has README and .gitignore only
- `first-try` branch has full project structure scaffolded
- Butler documentation seeded
- config.yaml template created (URLs TBD)

---

## Next Steps

1. **Inspect source pages** — visit the NATS SRD download page, VATSIM UK SCT page, and UK eAIP page to understand the HTML structure and link patterns. Document findings.
2. **Implement AIRAC cycle calculator** (`src/airac.py`) — pure date math, no network needed. Write tests.
3. **Implement directory manager** (`src/workspace/directory_manager.py`) — create cycle directories, conditional in.json copy-forward. Write tests.
4. **Implement first source fetcher** — pick the simplest one as proof of concept.

---

## Critical Rules

1. **config.yaml** stores all URLs and patterns — never hardcode download URLs in Python source.
2. **config.local.yaml** is gitignored — use it for user-specific path overrides.
3. **Main branch stays minimal** — all implementation work on `first-try` until ready to merge.
4. **The archive step does not auto-commit** — it stages files in the airac-data repo for the user to review before committing.
5. **in.json is never modified** — only copied forward from the previous cycle if the new directory doesn't already exist.
