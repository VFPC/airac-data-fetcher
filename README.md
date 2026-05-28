# AIRAC Data Fetcher

Python CLI tool that prepares the working directory for each AIRAC cycle in the [VFPC](https://github.com/VFPC) ecosystem.

This tool fetches and prepares source files. It does **not** run `New-SRDParser`, and it does **not** archive cycle data into `airac-data`.

## What it does

For a given AIRAC cycle, the tool:

1. Creates the cycle working directory (`vFPC YYNN/`)
2. Copies `in.json` forward from the previous cycle
3. Downloads the UK eAIP HTML files needed by downstream tools
4. Downloads the NATS SRD workbook and converts it to `Routes.csv` and `Notes.csv`
5. Downloads the VATSIM UK sector file (`.sct`)
6. Attempts to fetch Irish and French ENR 4.4 HTML as non-fatal support inputs
7. Attempts to fetch the Irish ENR 4.4 PDF as a non-fatal support input

After `fetch` completes:

- run [VFPC/New-SRDParser](https://github.com/VFPC/New-SRDParser) to produce `out.json`
- if you want to archive the cycle, run [VFPC/airac-archiver](https://github.com/VFPC/airac-archiver)

## Related repos

| Repo | Purpose |
|------|---------|
| [VFPC/New-SRDParser](https://github.com/VFPC/New-SRDParser) | Reads `Routes.csv`, `.sct`, and `in.json` to produce `out.json` |
| [VFPC/AIP-Parser](https://github.com/VFPC/AIP-Parser) | Reads the fetched eAIP HTML files |
| [VFPC/airac-archiver](https://github.com/VFPC/airac-archiver) | Copies allowlisted flat files into `airac-data` and stages them for review |
| [VFPC/airac-data](https://github.com/VFPC/airac-data) | Long-term archive of prepared cycle files |
| [VFPC/vFPC-Hub](https://github.com/VFPC/vFPC-Hub) | Shared project hub, rules reference, and Butler coordination |

---

## Prerequisites

- Python 3.11 or later

Install Python dependencies:

```
pip install -r requirements.txt
```

---

## Configuration

All configuration lives in `config.yaml` at the project root. Create a `config.local.yaml` alongside it (gitignored) for your machine-specific path overrides.

### Minimum config.local.yaml

```yaml
workspace_base: "C:\\path\\to\\your\\vFPC files"
```

- `workspace_base` — directory where per-cycle working folders are created. Each cycle gets a subfolder named `vFPC YYNN` (for example `vFPC 2603`).

### Full config reference

```yaml
workspace_base: ""          # required — override in config.local.yaml

sources:
  nats_srd:
    page_url:    "https://..."  # informational only — SRD zip URL is computed
    sheet_name:  "Routes"       # [RULE:SRD-EXCEL-STRUCTURE] NATS sheet name
    notes_sheet: "Notes"        # [RULE:SRD-EXCEL-STRUCTURE] NATS sheet name
  vatsim_sct:
    url:         ""             # reserved — not currently used
  eaip:
    page_url:    "https://..."  # NATS AIP index page URL
    files:
      - "EG-ENR-3.2-en-GB.html"
      - "EG-ENR-3.3-en-GB.html"
      - "EG-ENR-4.1-en-GB.html"
      - "EG-ENR-4.2-en-GB.html"
      - "EG-ENR-4.4-en-GB.html"
  irish_eaip:
    html_base_url: "https://..."  # AirNav Ireland AIRAC portal base
    page_url:    "https://..."  # AirNav Ireland IAIP package page
  french_eaip:
    base_url:    "https://..."  # SIA France eAIP DVD base
```

---

## Usage

Run the tool as a Python module from the project root.

### Fetch all source files for a cycle

```
python -m src fetch --cycle YYNN
```

Examples:

```
python -m src fetch --cycle 2603
python -m src fetch --cycle 2604
```

Omit `--cycle` to use the current active AIRAC cycle:

```
python -m src fetch
```

### What gets written to the working directory

| File | Source |
|------|--------|
| `in.json` | Copied forward from the previous cycle's directory |
| `EG-ENR-3.2-en-GB.html` | NATS AIP offline HTML download |
| `EG-ENR-3.3-en-GB.html` | NATS AIP offline HTML download |
| `EG-ENR-4.1-en-GB.html` | NATS AIP offline HTML download |
| `EG-ENR-4.2-en-GB.html` | NATS AIP offline HTML download |
| `EG-ENR-4.4-en-GB.html` | NATS AIP offline HTML download |
| `UK_YYYY_NN.sct` | VATSIM-UK uk-controller-pack release |
| `Routes.csv` | Converted from the NATS SRD Excel workbook |
| `Notes.csv` | Converted from the NATS SRD Excel workbook |
| `EI-ENR-4.4-en-IE.html` | AirNav Ireland eAIP cycle HTML fetch, when available |
| `FR-ENR-4.4-fr-FR.html` | SIA France eAIP cycle HTML fetch, when available |
| `EI_ENR_4_4_EN.pdf` | Irish IAIP package page fetch, when available |

---

## Typical workflow

```
# 1. Fetch source files into the cycle working directory
python -m src fetch --cycle 2603

# 2. Run New-SRDParser manually against that working directory
#    (this writes out.json into the cycle folder)

# 3. If you want to archive the cycle, run airac-archiver
#    in the separate airac-archiver repo
```

### About the dot releases in airac-data

The fetcher does **not** create `out.2603.1.json`, `out.2603.2.json`, and so on.

Those files are created later by `airac-archiver` when a cycle is archived. They are archive revisions of the **same AIRAC cycle**, not separate AIRAC cycles:

- `out.2603.1.json` = first archived parser output for AIRAC 2603
- `out.2603.2.json` = a later re-archive of AIRAC 2603 after a parser rerun or correction
- `out.2603.3.json` = another later archive of the same cycle

In other words, the number after the second dot is an archive version counter for that cycle.

---

## How source files are located

### eAIP HTML

The NATS AIP page ([nats-uk.ead-it.com](https://nats-uk.ead-it.com/cms-nats/opencms/en/Publications/AIP/)) lists each AIRAC cycle under a heading `AIRAC NN/YYYY`. The fetcher finds the heading matching the target cycle, follows the "Offline HTML Download" link, and extracts the required ENR HTML files from the downloaded archive. After extraction, the `EM.effectiveDateStart` meta tag in each file is checked against the cycle effective date. [`RULE:EAIP-PAGE-STRUCTURE`]

### NATS SRD

The SRD zip URL is fully deterministic: `AIRAC-{NN}-{YYYY}.zip` under the NATS Digital Datasets base path. No page scraping. The Excel file is identified by extension (`.xlsx` / `.xls`). [`RULE:SRD-DOWNLOAD-URL`]

After download, the "What's New" sheet header is read and the embedded date is validated against the cycle effective date. This catches wrong-cycle downloads before any CSV is written. [`RULE:SRD-EXCEL-STRUCTURE`]

### VATSIM UK sector file

The GitHub releases API for `VATSIM-UK/uk-controller-pack` is queried. The most recently published release whose tag matches `{YYYY}_{NN}[a-z]*` is selected (latest patch letter wins). The `.sct` file is extracted from `UK/data/UK_{YYYY}_{NN}.sct` inside the source archive. [`RULE:SCT-RELEASE-TAG`] [`RULE:SCT-FILE-PATH`]

### Foreign ENR 4.4 support files

Irish and French ENR 4.4 HTML files are fetched only after the provider's publication page exposes the target AIRAC cycle. AirNav Ireland is discovered from its AIRAC portal; SIA France is discovered from its eAIP product listing before the ENR 4.4 HTML path is derived. This prevents rehearsal runs for a future AIRAC from accidentally pulling the current cycle's foreign data. These fetches are non-fatal because the foreign AIP pages can lag during cycle turnover. [`RULE:IRISH-EAIP-ENR44-HTML-URL`] [`RULE:FRENCH-EAIP-ENR44-HTML-URL`]

---

## Error messages

All errors print a human-readable message and exit with a non-zero code. Common messages:

| Message | Cause |
|---------|-------|
| `Could not find heading 'AIRAC NN/YYYY' on AIP page` | NATS changed the page structure, or the cycle is not yet published |
| `HTTP 404 fetching SRD zip` | The SRD for this cycle is not yet available, or the URL pattern changed |
| `No GitHub release found for cycle YYNN` | VATSIM-UK has not yet published a release for this cycle |
| `SRD workbook date mismatch` | The downloaded Excel file is for a different cycle |

---

## Development

### Running tests

```
python -m pytest
```

The rules database validation test (`test_rules_db.py`) skips gracefully if neither `vFPC-Hub` nor the legacy `vFPC-Rules-Database` repo is cloned as a sibling of this repo.

### Project structure

```
src/
  airac.py                  AIRAC cycle date arithmetic
  config.py                 Config loader (config.yaml + config.local.yaml merge)
  cli.py                    Click entry point (`fetch` command)
  __main__.py               `python -m src` entry point
  sources/
    eaip_html.py            NATS AIP HTML fetcher
    foreign_enr44_html.py   Irish/French ENR 4.4 HTML support-file fetcher
    irish_eaip_pdf.py       Irish ENR 4.4 PDF fetcher
    nats_srd.py             NATS SRD Excel fetcher
    vatsim_sct.py           VATSIM UK SCT fetcher
  processing/
    excel_to_csv.py         SRD Excel to CSV converter and validator
    zip_handler.py          Shared HTTP zip downloader
  workspace/
    directory_manager.py    Cycle directory creation and in.json copy-forward
tests/
  test_airac.py
  test_config.py
  test_directory_manager.py
  test_eaip_html.py
  test_nats_srd.py
  test_vatsim_sct.py
  test_excel_to_csv.py
  test_cli.py
  test_rules_db.py
config.yaml                 Default configuration (safe to commit)
config.local.yaml           Machine-specific overrides (gitignored)
requirements.txt            Python dependencies
```
