"""Read settings from the process environment and the local, git-ignored `.env` file. ORIGIN: NEW.

Values in the real environment win over `.env`. Secrets read here are never logged or returned by the API.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"


def read_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    env = read_env_file(path)
    env.update({k: v for k, v in os.environ.items()})
    return env


def update_env_file(updates: dict[str, str], path: Path = ENV_FILE) -> None:
    """Set keys in `.env`, keeping every other line (e.g. MODEL_API_KEY) unchanged."""
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    done: set[str] = set()
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else None
        if key in updates:
            out.append(f"{key}={updates[key]}")
            done.add(key)
        else:
            out.append(line)
    for k, v in updates.items():
        if k not in done:
            out.append(f"{k}={v}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
