"""AI daily brief: the day's numbers -> Claude -> validated JSON (headline, 3-5 points, risks).

Division of labour: the code selects and computes every number; the model only writes text about them.
A checker refuses any number in the text that is not in the input (one retry with the error, then stop).
Without an API key, or if the call fails, the latest recorded brief is shown and labelled as such.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from . import analytics, config
from .build import BRIEF_FILE
from .llm import LLM, NoRecording

SYSTEM = (
    "You are a macro and markets analyst writing a short daily brief for a consulting team. "
    "Use ONLY the numbers in the input JSON and copy them exactly as written (same decimals); "
    "do not compute new numbers, do not convert units, do not add facts, dates or events that are not in the input. "
    "Plain English, no hype, no investment advice. Points: what moved and why it matters for Brazil and the US; "
    "mention the Focus expectations when they changed. Risks: what could change the picture. "
    "data_caveats: only items listed in data_quality (empty list if none)."
)

# 1,234.5 (thousands comma) | 5,22 (Portuguese decimal comma) | 13.75
_NUM = re.compile(r"(?<![A-Za-z])[-+]?(?:\d+,\d{1,2}(?![\d,])|\d+(?:,\d{3})*(?:\.\d+)?)")
_PT_DECIMAL = re.compile(r"^\d+,\d{1,2}$")


def numbers_in(text: str) -> list[str]:
    out = []
    for m in _NUM.finditer(text):
        n = m.group().lstrip("+-")
        out.append(n.replace(",", ".") if _PT_DECIMAL.match(n) else n.replace(",", ""))
    return out


def number_check(answer: dict, source: dict) -> list[str]:
    """Every number written by the model must exist in the input (rounding to fewer decimals allowed)."""
    allowed = {float(n) for n in numbers_in(json.dumps(source, ensure_ascii=False))}
    text = " ".join([answer.get("headline", "")] + answer.get("points", []) + answer.get("risks", [])
                    + answer.get("data_caveats", []))
    bad = []
    for n in numbers_in(text):
        x = float(n)
        nd = len(n.split(".")[1]) if "." in n else 0
        if not any(abs(x - a) < 1e-9 or round(a, nd) == x for a in allowed):
            bad.append(n)
    return [f"numbers not found in the input data: {sorted(set(bad))}"] if bad else []


def build_input(data: dict) -> dict:
    """Small, explicit input: the code decides what the model sees (all values pre-rounded)."""
    m = data.get("macro", {})
    pick = lambda rows: [{"indicator": r["label"], "value": r["last"], "unit": r["unit"], "change": r["chg"],
                          "date": r["date"]} for r in rows]
    wl = [w for w in data.get("watchlist", []) if w.get("chg_pct") is not None]
    stocks = sorted([w for w in wl if w["region"] in ("BR", "US")], key=lambda w: w["chg_pct"])
    risk_rows = []
    for region, r in (data.get("risk") or {}).items():
        if r["rows"]:
            hi = max(r["rows"], key=lambda x: x["vol"] or 0)
            risk_rows.append({"region": region, "highest_volatility": hi["ticker"], "vol_annual_pct": hi["vol"],
                              "risk_free_pct": r["rf"]})
    quality = [f"{k}: {s['status']} (last good copy {str(s.get('fetched_at') or 'never')[:10]})"
               for k, s in (data.get("status") or {}).items() if s.get("status") != "live"]
    return {
        "as_of": data.get("as_of"),
        "brazil_macro": pick(m.get("br", [])),
        "us_macro": pick(m.get("us", [])),
        "focus_expectations": [{"indicator": f["label"], "year": f["year"], "median": f["median"],
                                "change_4_weeks": f["chg_4w"]} for f in m.get("focus", [])],
        "indices_and_fx": [{"name": w["name"], "close": w["last"], "change_pct": w["chg_pct"]}
                           for w in wl if w["region"] in ("IDX", "FX")],
        "top_gainers": [{"ticker": w["ticker"], "change_pct": w["chg_pct"]} for w in stocks[::-1][:3]],
        "top_losers": [{"ticker": w["ticker"], "change_pct": w["chg_pct"]} for w in stocks[:3]],
        "risk": risk_rows,
        "data_quality": quality,
    }


def _schema(name: str) -> dict:
    return json.loads((config.SCHEMAS / f"brief.{name}.json").read_text(encoding="utf-8"))


def latest_recording(recordings: Path = config.RECORDINGS) -> dict | None:
    recs = sorted(recordings.glob("brief-*.json"), key=lambda p: json.loads(p.read_text(encoding="utf-8"))["recorded_at"])
    return json.loads(recs[-1].read_text(encoding="utf-8")) if recs else None


def run_brief(mode: str = "auto", today: date | None = None, out: Path = BRIEF_FILE, client=None,
              recordings: Path = config.RECORDINGS, cache_root: Path = config.CACHE) -> dict:
    data = analytics.json_safe(analytics.payload(today, cache_root))
    source = build_input(data)
    prompt = "Input data for today's brief (JSON):\n" + json.dumps(source, ensure_ascii=False, indent=1)
    llm = LLM(mode=mode, client=client, recordings=recordings)
    meta = {"model": config.MODEL}
    try:
        answer, info = llm.ask("brief", SYSTEM, prompt, _schema("api"), _schema("strict"),
                               check=lambda a: number_check(a, source))
        meta.update(info, number_check="passed")
    except Exception as e:  # noqa: BLE001  no key, no recording, API down, cap reached, failed checks
        rec = latest_recording(recordings)
        if rec is None:
            print(f"brief: not available ({type(e).__name__}: {e})")
            return {}
        answer = rec["answer"]
        meta.update(mode="recorded (latest available)", recorded_at=rec["recorded_at"],
                    input_tokens=rec.get("input_tokens"), output_tokens=rec.get("output_tokens"),
                    number_check="passed when recorded", note=f"{type(e).__name__}: {str(e)[:160]}")
    meta["input_hash"] = meta.pop("request", None) or "—"
    meta["cost_usd"] = round(llm.cost_usd(meta.get("input_tokens"), meta.get("output_tokens")), 6) \
        if meta.get("input_tokens") is not None else None
    result = {"date": data.get("as_of"), "brief": answer, "meta": meta, "input": source}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"brief: {meta['mode']} · {meta.get('input_tokens')} in / {meta.get('output_tokens')} out tokens · "
          f"api calls this run: {llm.calls}")
    return result
