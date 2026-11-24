"""Load PitConfig parameter files from controller/configs/."""

from __future__ import annotations

import math
from dataclasses import fields
from pathlib import Path

import yaml

from .pit_state_machine import PitConfig

CONFIG_DIR = Path(__file__).resolve().parent / "configs"

# Fields stored in degrees (or deg/s) in the YAML files, radians in PitConfig.
ANGLE_FIELDS = frozenset({
    "heading_tolerance", "pit_max_yaw_rate", "pit_max_slip", "pit_max_heading_error",
    "stable_yaw_rate", "stable_heading_error", "spin_heading",
})


def resolve_config_path(name_or_path: str | Path) -> Path:
    """A path to an existing file, or a name in controller/configs/ (``.yaml`` optional)."""
    path = Path(name_or_path)
    if path.is_file():
        return path.resolve()
    candidate = CONFIG_DIR / (path.name if path.suffix else f"{path.name}.yaml")
    if candidate.is_file():
        return candidate
    available = ", ".join(sorted(p.stem for p in CONFIG_DIR.glob("*.yaml"))) or "none"
    raise FileNotFoundError(f"No PIT config {name_or_path!r}. Available: {available}.")


def load_pit_overrides(name_or_path: str | Path) -> dict:
    """Read a parameter file into PitConfig keyword arguments (angles in radians)."""
    path = resolve_config_path(name_or_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping of PitConfig fields.")
    valid = {f.name for f in fields(PitConfig)}
    unknown = sorted(set(data) - valid)
    if unknown:
        raise ValueError(f"{path.name}: unknown PitConfig field(s): {', '.join(unknown)}")
    overrides = {}
    for key, value in data.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{path.name}: {key} must be a number, got {value!r}.")
        overrides[key] = math.radians(value) if key in ANGLE_FIELDS else value
    return overrides
