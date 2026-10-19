"""Weekly newsletter: the latest AI brief + three charts + the week's numbers, in Markdown and HTML.
No extra API call: it reuses the brief already written (and checked). Charts are plain SVG written here,
so the edition renders on GitHub, in a browser and in most mail clients without any library."""
from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

import pandas as pd

from . import analytics, cache, config
from .build import BRIEF_FILE

COLORS = ["#d9730d", "#1f6fb2", "#4a4a4a"]


# ---------------------------------------------------------------- charts
def line_svg(title: str, unit: str, lines: list[tuple[str, pd.Series]], width: int = 640, height: int = 240) -> str:
    """Line chart as an SVG string. lines: (label, series indexed by date)."""
    pad_l, pad_r, pad_t, pad_b = 46, 12, 34, 26
    lines = [(lab, s.dropna()) for lab, s in lines if s is not None and len(s.dropna()) > 1]
    if not lines:
        return ""
    x0 = min(s.index.min() for _, s in lines)
    x1 = max(s.index.max() for _, s in lines)
    lo = min(s.min() for _, s in lines)
    hi = max(s.max() for _, s in lines)
    m = (hi - lo) * 0.08 or 1
    lo, hi = lo - m, hi + m
    span = (x1 - x0).days or 1
    X = lambda d: pad_l + (d - x0).days / span * (width - pad_l - pad_r)
    Y = lambda v: pad_t + (1 - (v - lo) / (hi - lo)) * (height - pad_t - pad_b)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
           f'font-family="Helvetica, Arial, sans-serif" font-size="11" role="img" aria-label="{html.escape(title)}">',
           f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
           f'<text x="{pad_l}" y="14" font-size="13" font-weight="bold" fill="#222">{html.escape(title)}</text>',
           f'<text x="{width - pad_r}" y="14" text-anchor="end" fill="#777">{html.escape(unit)}</text>']
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        y = Y(v)
        out.append(f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e6e6e6"/>')
        out.append(f'<text x="{pad_l - 6}" y="{y + 4:.1f}" text-anchor="end" fill="#777">{v:,.2f}</text>')
    for i in range(5):
        d = x0 + (x1 - x0) * i / 4
        anchor = "start" if i == 0 else "end" if i == 4 else "middle"
        out.append(f'<text x="{X(d):.1f}" y="{height - 8}" text-anchor="{anchor}" fill="#777">{d:%b %y}</text>')
    for k, (lab, s) in enumerate(lines):
        pts = " ".join(f"{X(d):.1f},{Y(v):.1f}" for d, v in s.items())
        out.append(f'<polyline fill="none" stroke="{COLORS[k]}" stroke-width="2" points="{pts}"/>')
        lx = pad_l + 8 + k * 170
        out.append(f'<rect x="{lx}" y="22" width="12" height="3" fill="{COLORS[k]}"/>'
                   f'<text x="{lx + 16}" y="27" fill="#333">{html.escape(lab)} {s.iloc[-1]:,.2f}</text>')
    out.append("</svg>")
    return "\n".join(out)


def _series(df: pd.DataFrame | None, key: str, col: str = "series") -> pd.Series | None:
    if df is None or df.empty:
        return None
    s = df[df[col] == key].assign(date=lambda d: pd.to_datetime(d["date"])).set_index("date")
    return s["value" if "value" in s else "close"].sort_index()


def charts(cache_root: Path = config.CACHE) -> dict[str, str]:
    br, prices = cache.load("macro_br", cache_root), cache.load("prices", cache_root)
    out = {}
    sel, ipca = _series(br, "selic_target"), _series(br, "ipca_12m")
    if sel is not None and ipca is not None:
        start = ipca.index.max() - pd.DateOffset(months=24)
        out["rates"] = line_svg("Selic target vs IPCA 12m, 2 years", "% (BCB SGS 432, 13522)",
                                [("Selic", sel.resample("MS").last()[start:]), ("IPCA 12m", ipca[start:])])
    fx = _series(br, "usdbrl_ptax")
    if fx is not None:
        out["fx"] = line_svg("USD/BRL PTAX, 6 months", "BRL per USD (BCB SGS 1)", [("PTAX", fx[fx.index.max() - pd.DateOffset(months=6):])])
    if prices is not None:
        idx = {t: _series(prices, t, "ticker") for t in ("IBOV", "SPX")}
        if all(s is not None for s in idx.values()):
            start = max(s.index.max() for s in idx.values()) - pd.DateOffset(months=6)
            reb = [(n, s[start:] / s[start:].iloc[0] * 100) for n, s in (("Ibovespa", idx["IBOV"]), ("S&P 500", idx["SPX"]))]
            out["indices"] = line_svg("Ibovespa vs S&P 500, 6 months", "rebased to 100 (Yahoo Finance)", reb)
    return {k: v for k, v in out.items() if v}


# ---------------------------------------------------------------- edition
def _row(cells: list) -> str:
    return "| " + " | ".join("—" if c is None else str(c) for c in cells) + " |"


def render_md(brief: dict, data: dict, chart_files: dict[str, str]) -> str:
    b = brief["brief"]
    m = data.get("macro", {})
    lines = [f"# Macro Terminal weekly · {brief['date']}", "", f"**{b['headline']}**", ""]
    lines += [f"- {p}" for p in b["points"]]
    lines += ["", "**Risks to watch**", ""] + [f"- {r}" for r in b["risks"]]
    if b.get("data_caveats"):
        lines += ["", "**Data caveats**", ""] + [f"- {c}" for c in b["data_caveats"]]
    if data.get("alerts"):
        lines += ["", "**Alerts**", ""] + [f"- {a['text']}" for a in data["alerts"]]
    lines += ["", "## Charts", ""] + [f"![{k}]({v})" for k, v in chart_files.items()]
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


def render_html(brief: dict, data: dict, svgs: dict[str, str]) -> str:
    b, e = brief["brief"], html.escape
    m = data.get("macro", {})
    table = lambda rows: ("<table><tr><th>Indicator</th><th>Last</th><th>Change</th><th>Date</th></tr>" + "".join(
        f"<tr><td>{e(r['label'])}</td><td class=n>{r['last']}</td><td class=n>{'' if r['chg'] is None else r['chg']}</td>"
        f"<td>{e(r['date'])}</td></tr>" for r in rows) + "</table>")
    alerts = "".join(f"<li>{e(a['text'])}</li>" for a in data.get("alerts", []))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Macro Terminal weekly · {e(brief['date'])}</title>
<style>
body {{ margin: 0; background: #f4f1ec; color: #222; font: 15px/1.55 Helvetica, Arial, sans-serif; }}
main {{ max-width: 680px; margin: 0 auto; background: #fff; padding: 24px 20px 32px; }}
.k {{ background: #d9730d; color: #fff; font-size: 11px; letter-spacing: 1px; padding: 2px 6px; }}
h1 {{ font-size: 22px; margin: 10px 0 4px; }} h2 {{ font-size: 15px; color: #d9730d; text-transform: uppercase;
letter-spacing: 1px; border-bottom: 1px solid #eee; padding-bottom: 4px; margin-top: 26px; }}
li {{ margin: 4px 0; }} svg {{ max-width: 100%; height: auto; display: block; margin: 10px 0; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }} td, th {{ border-bottom: 1px solid #eee; padding: 4px 6px; text-align: left; }}
td.n {{ text-align: right; font-variant-numeric: tabular-nums; }} .foot {{ color: #777; font-size: 12px; margin-top: 24px; }}
</style></head><body><main>
<span class="k">MACRO TERMINAL · WEEKLY</span><div style="color:#777;font-size:13px;margin-top:6px">{e(brief['date'])}</div>
<h1>{e(b['headline'])}</h1>
<ul>{''.join(f'<li>{e(p)}</li>' for p in b['points'])}</ul>
<h2>Risks to watch</h2><ul>{''.join(f'<li>{e(r)}</li>' for r in b['risks'])}</ul>
{f'<h2>Alerts</h2><ul>{alerts}</ul>' if alerts else ''}
<h2>Charts</h2>{''.join(svgs.values())}
<h2>Brazil</h2>{table(m.get('br', []))}
<h2>United States</h2>{table(m.get('us', []))}
<p class="foot">Text written by {e(str(brief.get('meta', {}).get('model')))} from these numbers; every number in it was
checked against the input data. Sources: BCB, FRED, Yahoo Finance, CVM. Not investment advice.</p>
</main></body></html>
"""


def write_newsletter(brief_path: Path = BRIEF_FILE, out_dir: Path = config.NEWSLETTER,
                     today: date | None = None, cache_root: Path = config.CACHE) -> Path | None:
    if not brief_path.exists():
        return None
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    data = analytics.json_safe(analytics.payload(today, cache_root))
    d = date.fromisoformat(brief["date"]) if brief.get("date") else date.today()
    year, week, _ = d.isocalendar()
    name = f"{year}-W{week:02d}"
    svgs = charts(cache_root)
    (out_dir / name).mkdir(parents=True, exist_ok=True)
    files = {}
    for k, svg in svgs.items():
        (out_dir / name / f"{k}.svg").write_text(svg, encoding="utf-8")
        files[k] = f"{name}/{k}.svg"
    (out_dir / f"{name}.md").write_text(render_md(brief, data, files), encoding="utf-8")
    path = out_dir / f"{name}.html"
    path.write_text(render_html(brief, data, svgs), encoding="utf-8")
    return path


def editions(out_dir: Path = config.NEWSLETTER) -> list[dict]:
    """Index of past editions for the NEWS tab (newest first)."""
    items = []
    for md in sorted(out_dir.glob("*-W*.md"), reverse=True):
        first = md.read_text(encoding="utf-8").splitlines()
        headline = next((l.strip("*") for l in first if l.startswith("**")), "")
        items.append({"week": md.stem, "date": first[0].split("·")[-1].strip() if first else "",
                      "headline": headline, "html": f"newsletter/{md.stem}.html", "md": f"newsletter/{md.stem}.md"})
    return items
