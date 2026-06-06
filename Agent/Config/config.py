"""Shared configuration loader — single source of truth for app_config.yaml and special_practices.yaml.

Usage:
    from Agent.Config.config import load_config, load_special_practices, get_project_root

    cfg = load_config()
    practices = load_special_practices()
    root = get_project_root()
"""
import yaml
from functools import lru_cache
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_project_root() -> Path:
    return _PROJECT_ROOT


@lru_cache(maxsize=1)
def load_config() -> dict:
    with open(_PROJECT_ROOT / "Agent" / "Config" / "app_config.yaml") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_special_practices() -> list[dict]:
    with open(_PROJECT_ROOT / "Agent" / "Config" / "special_practices.yaml") as f:
        return yaml.safe_load(f)
