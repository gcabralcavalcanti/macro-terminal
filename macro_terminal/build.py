"""Page template + data.js -> output/site/. Data is embedded as a script (not fetched) so the page opens from disk."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

from . import analytics, config

BRIEF_FILE = config.ROOT / "data" / "brief.json"
ASK_FILE = config.ROOT / "data" / "ask.json"


def load_brief(path: Path = BRIEF_FILE) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def latest(data: dict) -> dict:
    """Small machine-readable summary published next to the page (read by the n8n flow)."""
    brief = data.get("brief") or {}
    return {
        "generated_at": data.get("generated_at"),
        "as_of": data.get("as_of"),
        "brief_date": brief.get("date"),
        "headline": (brief.get("brief") or {}).get("headline"),
        "points": (brief.get("brief") or {}).get("points", []),
        "alerts": [a["text"] for a in data.get("alerts", [])],
        "stale_sources": [k for k, v in (data.get("status") or {}).items() if v.get("status") != "live"],
    }


def build(
    out: Path = config.SITE,
    today: date | None = None,
    cache_root: Path = config.CACHE,
    brief_path: Path = BRIEF_FILE,
    ask_path: Path = ASK_FILE,
    news_dir: Path = config.NEWSLETTER,
) -> Path:
    from .newsletter import editions

    data = analytics.payload(today, cache_root)
    data["brief"] = load_brief(brief_path)
    data["ask"] = load_brief(ask_path)
    data["newsletters"] = editions(news_dir)
    data["generated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    data = analytics.json_safe(data)
    out.mkdir(parents=True, exist_ok=True)
    for f in config.WEB.iterdir():
        if f.is_file():
            shutil.copy2(f, out / f.name)
    if news_dir.exists():  # past editions are served next to the page
        shutil.copytree(news_dir, out / "newsletter", dirs_exist_ok=True)
    js = "window.TERMINAL = " + json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + ";\n"
    (out / "data.js").write_text(js, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    (out / "latest.json").write_text(json.dumps(latest(data), ensure_ascii=False, indent=1), encoding="utf-8")
    return out / "index.html"
