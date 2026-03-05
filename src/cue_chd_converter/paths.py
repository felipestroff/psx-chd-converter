import sys
from pathlib import Path
from typing import List


def get_app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[2]


def get_chdman_candidates() -> List[Path]:
    base = get_app_base_dir()
    return [
        base / "tools" / "mame" / "chdman.exe",
        base / "mame" / "chdman.exe",
    ]


def resolve_chdman_path() -> Path:
    candidates = get_chdman_candidates()
    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]
