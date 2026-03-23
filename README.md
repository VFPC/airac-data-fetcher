# AIRAC Data Fetcher

Python CLI tool that automates the download, extraction, and preparation of input files needed for each AIRAC cycle in the [VFPC](https://github.com/VFPC) ecosystem. It replaces the manual steps in the AIRAC maintenance checklist.

## What it does

For a given AIRAC cycle, the tool:

1. Creates the cycle working directory (`vFPC YYNN/`)
2. Copies `in.json` forward from the previous cycle
3. Downloads the **UK eAIP** ENR-3.2 and ENR-3.3 HTML files from the NATS AIP page
4. Downloads the **NATS SRD** Excel workbook and converts it to `Routes.csv` and `Notes.csv`
5. Downloads the **VATSIM UK sector file** (`.sct`) from the uk-controller-pack GitHub release
6. After you run the SRD Parser: zips all files and stages them in `VFPC/airac-data` for review

## Related repos

| Repo | Purpose |
|------|---------|
| [VFPC/New-SRDParser](https://github.com/VFPC/New-SRDParser) | Reads `Routes.csv`, `.sct`, and `in.json` to produce `out.json` |
| [VFPC/AIP-Parser](https://github.com/VFPC/AIP-Parser) | Reads `EG-ENR-3.2-en-GB.html` and `EG-ENR-3.3-en-GB.html` |
| [VFPC/airac-data](https://github.com/VFPC/airac-data) | Long-term archive of prepared cycle files |
| [VFPC/vFPC-Rules-Database](https://github.com/VFPC/vFPC-Rules-Database) | Traceability index for aviation rules used in this tool |

---

## Prerequisites

- Python 3.11 or later
- Git (for the `archive` command's `git add` staging step)
- A local clone of [VFPC/airac-data](https://github.com/VFPC/airac-data)

Install Python dependencies:

```
pip install -r requirements.txt
```

---

## Configuration

All configuration lives in `config.yaml` at the project root. Create a `config.local.yaml` alongside it (gitignored) for your machine-specific paths — it deep-merges on top of `config.yaml` automatically.

### Minimum config.local.yaml

```yaml
workspace_base: "C:\\path\\to\\your\\vFPC files"
archive_repo:   "C:\\path\\to\\your\\airac-data"
```

- **`workspace_base`** — directory where per-cycle working folders are created. Each cycle gets a subfolder named `vFPC YYNN` (e.g. `vFPC 2603`).
- **`archive_repo`** — path to your local clone of `VFPC/airac-data`. The archiver writes the zip and manifest here and stages them with `git add`.

### Full config reference

```yaml
workspace_base: ""          # required — override in config.local.yaml
archive_repo:   ""          # required — override in config.local.yaml

sources:
  nats_srd:
    page_url:    "https://..."  # informational only — SRD zip URL is computed
                                # from the cycle ident, not from this field
    sheet_name:  "Routes"       # [RULE:SRD-EXCEL-STRUCTURE] NATS sheet name
    notes_sheet: "Notes"        # [RULE:SRD-EXCEL-STRUCTURE] NATS sheet name
  vatsim_sct:
    url:         ""             # reserved — not currently used
  eaip:
    page_url:    "https://..."  # NATS AIP index page URL — override here if
                                # NATS changes it; leave blank to use the
                                # hardcoded default in eaip_html.py
    files:
      - "EG-ENR-3.2-en-GB.html"
      - "EG-ENR-3.3-en-GB.html"
```

---

## Usage

Run the tool as a Python module from the project root.

### Fetch all source files for a cycle

```
python -m src fetch --cycle YYNN
```

Runs steps 1–6 in order. Prints progress for each step. Stops immediately on any error with a descriptive message.

**Examples:**

```
python -m src fetch --cycle 2603
python -m src fetch --cycle 2601
```

Omit `--cycle` to use the current active AIRAC cycle:

```
python -m src fetch
```

**What gets written to the working directory:**

| File | Source |
|------|--------|
| `in.json` | Copied forward from the previous cycle's directory |
| `EG-ENR-3.2-en-GB.html` | NATS AIP offline HTML download |
| `EG-ENR-3.3-en-GB.html` | NATS AIP offline HTML download |
| `UK_YYYY_NN.sct` | VATSIM-UK uk-controller-pack release |
| `Routes.csv` | Converted from the NATS SRD Excel workbook |
| `Notes.csv` | Converted from the NATS SRD Excel workbook |

### Archive a cycle

After `fetch` has completed and you have run the SRD Parser (so `out.json` is present):

```
python -m src archive --cycle YYNN
```

This:
- Collects all seven required files from the cycle working directory
- Creates `{archive_repo}/vFPC YYNN/vFPC YYNN.zip`
- Writes `{archive_repo}/vFPC YYNN/manifest.md`
- Runs `git add` on both files so they are staged for your review

Then review and commit in the `airac-data` repo when you are satisfied.

---

## Typical workflow

```
# 1. Fetch all source files
python -m src fetch --cycle 2603

# 2. Run New-SRDParser manually against the working directory
#    (this writes out.json into the cycle folder)

# 3. Run AIP-Parser manually if needed

# 4. Archive and stage
python -m src archive --cycle 2603

# 5. Review in the airac-data repo and commit
cd path\to\airac-data
git status
git commit -m "Add vFPC 2603 archive"
git push
```

---

## How source files are located

### eAIP HTML

The NATS AIP page ([nats-uk.ead-it.com](https://nats-uk.ead-it.com/cms-nats/opencms/en/Publications/AIP/)) lists each AIRAC cycle under a heading `AIRAC NN/YYYY`. The fetcher finds the heading matching the target cycle, follows the "Offline HTML Download" link, and extracts `EG-ENR-3.2-en-GB.html` and `EG-ENR-3.3-en-GB.html` from the zip. After extraction, the `EM.effectiveDateStart` meta tag in each file is checked against the cycle effective date. [`RULE:EAIP-PAGE-STRUCTURE`]

### NATS SRD

The SRD zip URL is fully deterministic: `AIRAC-{NN}-{YYYY}.zip` under the NATS Digital Datasets base path. No page scraping. The Excel file is identified by extension (`.xlsx` / `.xls`). [`RULE:SRD-DOWNLOAD-URL`]

After download, the "What's New" sheet header is read and the embedded date is validated against the cycle effective date. This catches wrong-cycle downloads before any CSV is written. [`RULE:SRD-EXCEL-STRUCTURE`]

### VATSIM UK sector file

The GitHub releases API for `VATSIM-UK/uk-controller-pack` is queried. The most recently published release whose tag matches `{YYYY}_{NN}[a-z]*` is selected (latest patch letter wins). The `.sct` file is extracted from `UK/data/UK_{YYYY}_{NN}.sct` inside the source zip. [`RULE:SCT-RELEASE-TAG`] [`RULE:SCT-FILE-PATH`]

---

## Error messages

All errors print a human-readable message and exit with a non-zero code. Common messages:

| Message | Cause |
|---------|-------|
| `Could not find heading 'AIRAC NN/YYYY' on AIP page` | NATS changed the page structure, or the cycle is not yet published |
| `HTTP 404 fetching SRD zip` | The SRD for this cycle is not yet available, or the URL pattern changed |
| `No GitHub release found for cycle YYNN` | VATSIM-UK has not yet published a release for this cycle |
| `SRD workbook date mismatch` | The downloaded Excel file is for a different cycle — check the NATS page |
| `Cannot archive cycle YYNN — missing files` | One or more required files are missing; check that `fetch` completed and `out.json` was written by the SRD Parser |
| `git add failed` | The `archive_repo` path is not a valid git repository, or git is not on the PATH |

---

## Development

### Running tests

```
python -m pytest
```

All 265 tests should pass. The rules database validation test (`test_rules_db.py`) skips gracefully if `vFPC-Rules-Database` is not cloned as a sibling of this repo.

### Project structure

```
src/
  airac.py                  AIRAC cycle date arithmetic
  config.py                 Config loader (config.yaml + config.local.yaml merge)
  cli.py                    Click entry point (fetch / archive commands)
  __main__.py               python -m src entry point
  sources/
    eaip_html.py            NATS AIP HTML fetcher
    nats_srd.py             NATS SRD Excel fetcher
    vatsim_sct.py           VATSIM UK SCT fetcher
  processing/
    excel_to_csv.py         SRD Excel → CSV converter and validator
    zip_handler.py          Shared HTTP zip downloader
  workspace/
    directory_manager.py    Cycle directory creation and in.json copy-forward
  archive/
    archiver.py             Zip creation, manifest writing, git staging
tests/
  test_airac.py             (29 tests)
  test_config.py            (22 tests)
  test_directory_manager.py (19 tests)
  test_eaip_html.py         (25 tests)
  test_nats_srd.py          (22 tests)
  test_vatsim_sct.py        (35 tests)
  test_excel_to_csv.py      (28 tests)
  test_archiver.py          (45 tests)
  test_cli.py               (38 tests)
  test_rules_db.py          (2 tests — skips if vFPC-Rules-Database not present)
config.yaml                 Default configuration (safe to commit)
config.local.yaml           Machine-specific overrides (gitignored)
requirements.txt            Python dependencies
```

### Adding a new AIRAC rule

If code is added that depends on a NATS/ICAO/CAA publishing convention, tag it with `[RULE:NAME]` and register it in `vFPC-Rules-Database/Documentation/rules_reference.md`. See the [convention document](https://github.com/VFPC/vFPC-Rules-Database/blob/main/Documentation/convention.md) for the full process. The `test_rules_db.py` test will catch any unregistered tags.
