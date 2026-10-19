"""Weekly newsletter in Markdown: the latest AI brief plus a table of the week's numbers.
No extra API call: it reuses the brief already written (and checked) for the day."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import analytics, config
from .build import BRIEF_FILE


def _row(cells: list) -> str:
    return "| " + " | ".join("—" if c is None else str(c) for c in cells) + " |"


def render(brief: dict, data: dict) -> str:
    b = brief["brief"]
    m = data.get("macro", {})
    lines = [f"# Macro Terminal weekly · {brief['date']}", "", f"**{b['headline']}**", ""]
    lines += [f"- {p}" for p in b["points"]]
    lines += ["", "**Risks to watch**", ""] + [f"- {r}" for r in b["risks"]]
    if b.get("data_caveats"):
        lines += ["", "**Data caveats**", ""] + [f"- {c}" for c in b["data_caveats"]]
    for title, rows in (("Brazil", m.get("br", [])), ("United States", m.get("us", []))):
        lines += ["", f"## {title}", "", _row(["Indicator", "Last", "Change", "Date"]), _row(["---"] * 4)]
        lines += [_row([r["label"], r["last"], r["chg"], r["date"]]) for r in rows]
    stocks = [w for w in data.get("watchlist", []) if w.get("chg_pct") is not None]
    lines += ["", "## Markets (last session)", "", _row(["Ticker", "Close", "1D %"]), _row(["---"] * 3)]
    lines += [_row([w["ticker"], w["last"], w["chg_pct"]]) for w in stocks]
    meta = brief.get("meta", {})
    lines += ["", "---", f"Text written by {meta.get('model')} from the numbers above; every number in it was checked "
              "against the input data. Sources: BCB, FRED, Yahoo Finance, CVM. Not investment advice.", ""]
    return "\n".join(lines)


def write_newsletter(brief_path: Path = BRIEF_FILE, out_dir: Path = config.NEWSLETTER,
                     today: date | None = None, cache_root: Path = config.CACHE) -> Path | None:
    if not brief_path.exists():
        return None
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    data = analytics.json_safe(analytics.payload(today, cache_root))
    d = date.fromisoformat(brief["date"]) if brief.get("date") else date.today()
    year, week, _ = d.isocalendar()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{year}-W{week:02d}.md"
    path.write_text(render(brief, data), encoding="utf-8")
    return path
