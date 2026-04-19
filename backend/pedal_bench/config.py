"""Runtime configuration — paths, env vars, server host/port.

Reads from environment with sensible local-dev defaults.
"""

from __future__ import annotations

import os
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent        # backend/
REPO_ROOT = _BACKEND_DIR.parent                              # pedal-bench/

DATA_DIR: Path = Path(__file__).resolve().parent / "data"

PROJECTS_DIR: Path = Path(
    os.getenv("PEDAL_BENCH_PROJECTS_DIR", REPO_ROOT / "projects")
)
INVENTORY_FILE: Path = Path(
    os.getenv("PEDAL_BENCH_INVENTORY", REPO_ROOT / "inventory.json")
)

HOST: str = os.getenv("PEDAL_BENCH_HOST", "127.0.0.1")
PORT: int = int(os.getenv("PEDAL_BENCH_PORT", "8642"))    # 1337 + 8080 // 2, ish

# CORS origins for local dev. Production serves frontend from same origin.
DEV_CORS_ORIGINS: list[str] = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def enclosures_path() -> Path:
    return DATA_DIR / "enclosures.json"


def suppliers_path() -> Path:
    return DATA_DIR / "suppliers.json"


def orientation_hints_path() -> Path:
    return DATA_DIR / "orientation_hints.json"
