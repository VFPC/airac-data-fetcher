# AIRAC Data Fetcher

Python CLI tool to automate AIRAC cycle data acquisition for the [VFPC](https://github.com/VFPC) ecosystem.

Downloads, extracts, and prepares input files needed by:
- [New-SRDParser](https://github.com/VFPC/New-SRDParser) — SRD CSV, SCT sector file, in.json
- [AIP-Parser](https://github.com/VFPC/AIP-Parser) — UK eAIP ENR 3.2/3.3 HTML files

Prepared files can be archived to [airac-data](https://github.com/VFPC/airac-data) for long-term version-controlled storage.

## Status

Under development on the `first-try` branch.

## Related repos

| Repo | Purpose |
|------|---------|
| [VFPC/New-SRDParser](https://github.com/VFPC/New-SRDParser) | Parses UK SRD into structured JSON for the vFPC plugin |
| [VFPC/AIP-Parser](https://github.com/VFPC/AIP-Parser) | Parses UK AIP ENR 3.2/3.3 into segment data for MC resolution |
| [VFPC/airac-data](https://github.com/VFPC/airac-data) | Long-term archive of AIRAC cycle input data |
| [VFPC/vFPC-Rules-Database](https://github.com/VFPC/vFPC-Rules-Database) | Aviation rules traceability index |
