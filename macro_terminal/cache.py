"""Local cache: the last good copy of each dataset plus a status file.

data/cache/<dataset>.csv   last version that passed the checks
data/cache/_status.json    per dataset: source, fetched_at, rows, last_date, status (live | stale | missing), issues
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from . import config


def _status_path(root: Path) -> Path:
    return root / "_status.json"


def read_status(root: Path = config.CACHE) -> dict:
    p = _status_path(root)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _write_status(status: dict, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _status_path(root).write_text(json.dumps(status, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def load(name: str, root: Path = config.CACHE) -> pd.DataFrame | None:
    p = root / f"{name}.csv"
    return pd.read_csv(p) if p.exists() else None


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def save(
    name: str,
    df: pd.DataFrame,
    source: str,
    issues: list[dict],
    root: Path = config.CACHE,
    date_col: str | None = "date",
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    df.to_csv(root / f"{name}.csv", index=False)
    status = read_status(root)
    last = str(pd.to_datetime(df[date_col]).max().date()) if date_col and date_col in df else None
    status[name] = {
        "source": source,
        "status": "live",
        "fetched_at": now_iso(),
        "attempted_at": now_iso(),
        "rows": int(len(df)),
        "last_date": last,
        "issues": issues,
        "error": None,
    }
    _write_status(status, root)


def mark_failed(
    name: str, source: str, error: str, issues: list[dict] | None = None, root: Path = config.CACHE
) -> None:
    """Keep the old file; record that today's attempt failed."""
    status = read_status(root)
    old = status.get(name, {})
    has_cache = (root / f"{name}.csv").exists()
    status[name] = {
        **old,
        "source": source,
        "status": "stale" if has_cache else "missing",
        "attempted_at": now_iso(),
        "error": error[:300],
        "issues": issues or old.get("issues", []),
    }
    status[name].setdefault("fetched_at", None)
    _write_status(status, root)
