"""Load and validate config.yaml / config.local.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

# config.yaml lives at the project root, one level above this file.
_PROJECT_ROOT = Path(__file__).parent.parent


class ConfigError(ValueError):
    """Raised when config.yaml is missing, unreadable, or fails validation."""


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NatsSrdConfig:
    page_url: str
    sheet_name: str
    notes_sheet: str


@dataclass(frozen=True)
class VatsimSctConfig:
    url: str


@dataclass(frozen=True)
class EaipConfig:
    page_url: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class SourcesConfig:
    nats_srd: NatsSrdConfig
    vatsim_sct: VatsimSctConfig
    eaip: EaipConfig


@dataclass(frozen=True)
class Config:
    workspace_base: Path
    sources: SourcesConfig


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> dict:
    """Return a new dict with *override* recursively merged on top of *base*."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _require_str(raw: dict, *keys: str) -> str:
    """Walk *raw* by *keys* and return the value, raising ConfigError if absent or empty."""
    node: object = raw
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(f"Required config key '{'.'.join(keys)}' is missing.")
        node = node[key]
    if not node:
        raise ConfigError(f"Required config key '{'.'.join(keys)}' must not be empty.")
    return str(node)


def _parse(raw: dict) -> Config:
    workspace_base = Path(_require_str(raw, "workspace_base"))

    src = raw.get("sources") or {}

    srd = src.get("nats_srd") or {}
    nats_srd = NatsSrdConfig(
        page_url=srd.get("page_url") or "",
        # [RULE:SRD-EXCEL-STRUCTURE] sheet names are NATS publishing conventions
        sheet_name=srd.get("sheet_name") or "Routes",
        notes_sheet=srd.get("notes_sheet") or "Notes",
    )

    sct = src.get("vatsim_sct") or {}
    vatsim_sct = VatsimSctConfig(url=sct.get("url") or "")

    eaip = src.get("eaip") or {}
    eaip_cfg = EaipConfig(
        page_url=eaip.get("page_url") or "",
        files=tuple(eaip.get("files") or []),
    )

    return Config(
        workspace_base=workspace_base,
        sources=SourcesConfig(
            nats_srd=nats_srd,
            vatsim_sct=vatsim_sct,
            eaip=eaip_cfg,
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load(config_path: Path | None = None) -> Config:
    """Load and return the merged configuration.

    Reads *config_path* (defaults to ``config.yaml`` in the project root).
    If a sibling ``config.local.yaml`` exists it is deep-merged on top,
    allowing per-machine path overrides without touching the committed file.

    Raises ``ConfigError`` if the file is missing, unparseable, or required
    keys are absent.
    """
    base_path = config_path if config_path is not None else _PROJECT_ROOT / "config.yaml"

    if not base_path.exists():
        raise ConfigError(f"Config file not found: {base_path}")

    try:
        raw: dict = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse {base_path}: {exc}") from exc

    local_path = base_path.with_name("config.local.yaml")
    if local_path.exists():
        try:
            local_raw: dict = yaml.safe_load(local_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"Failed to parse {local_path}: {exc}") from exc
        raw = _deep_merge(raw, local_raw)

    return _parse(raw)
