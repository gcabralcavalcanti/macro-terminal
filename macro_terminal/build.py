"""Static site generation: web/ template + data.js -> site/.

The data goes into data.js as `window.TERMINAL = {...}` (not a fetch of data.json), so the page also
opens straight from disk (file://) with no server. GitHub Pages serves the same folder.
"""
from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

from . import analytics, config

BRIEF_FILE = config.ROOT / "data" / "brief.json"


def load_brief(path: Path = BRIEF_FILE) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def build(out: Path = config.SITE, today: date | None = None, cache_root: Path = config.CACHE,
          brief_path: Path = BRIEF_FILE) -> Path:
    data = analytics.payload(today, cache_root)
    data["brief"] = load_brief(brief_path)
    data["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data = analytics.json_safe(data)
    out.mkdir(parents=True, exist_ok=True)
    for f in config.WEB.iterdir():
        if f.is_file():
            shutil.copy2(f, out / f.name)
    js = "window.TERMINAL = " + json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + ";\n"
    (out / "data.js").write_text(js, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return out / "index.html"
