"""Load config.yaml once and expose absolute, typed paths."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# this file is ROOT/src/hmci/common/config.py -> go up 3 levels to reach ROOT
ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "config.yaml"


@dataclass(frozen=True)
class Paths:
    raw: Path
    interim: Path
    processed: Path
    warehouse: Path
    reports: Path

    def make_dirs(self) -> None:
        """Create every output folder if it does not exist yet."""
        for p in (self.raw, self.interim, self.processed, self.reports):
            p.mkdir(parents=True, exist_ok=True)
        self.warehouse.parent.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Config:
    raw: dict[str, Any]   # the full YAML, for anything not wrapped below
    paths: Paths

    @property
    def seed(self) -> int:
        return int(self.raw["project"]["seed"])


@lru_cache(maxsize=1)
def load_config(path: Path = CONFIG_PATH) -> Config:
    with open(path) as f:
        raw = yaml.safe_load(f)
    paths = Paths(**{key: ROOT / value for key, value in raw["paths"].items()})
    return Config(raw=raw, paths=paths)