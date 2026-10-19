"""ASK: a question in plain language about today's data, answered by Claude with the series it used.

- The code builds a small context: recent history of each series (weekly or monthly points), with an id per series.
- The answer must list the ids it relied on (an enum in the schema, so it cannot cite a series that does not exist)
  and every number in the text must exist in the context (same check as the brief). One retry, then stop.
- The public page shows preset questions answered on the scheduled run; live questions run only on the
  author's machine (`python -m macro_terminal ask "..."` or the local server in `serve.py`).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from . import analytics, cache, config
from .brief import number_check
from .llm import LLM

ASK_FILE = config.ROOT / "data" / "ask.json"

PRESETS = [
    "Did Brazil's real interest rate go up or down over the last few months?",
    "O dólar subiu ou caiu contra o real nas últimas semanas?",
    "Are market inflation expectations for this year above the target ceiling?",
    "Is the US yield curve inverted?",
    "Which stocks were the most volatile over the last year, in Brazil and in the US?",
]

SYSTEM = (
    "You answer questions about a macro and markets dashboard using ONLY the JSON context. "
    "Copy numbers exactly as written in the context; do not compute new numbers except simple comparisons in words "
    "(higher, lower, unchanged). Cite in series_used the ids of every series you relied on. "
    "If the context does not contain what is needed, set cannot_answer to true and say what is missing. "
    "Answer in the language of the question, in at most 4 sentences. No investment advice."
)


def _points(df: pd.DataFrame, key: str, rule: str | None, n: int) -> list[list]:
    s = df[df["series"] == key].assign(date=lambda d: pd.to_datetime(d["date"])).set_index("date")["value"].dropna()
    if rule:  # last observation of each week, keeping its real date (not the end-of-week label)
        s = s.groupby(s.index.to_period(rule)).tail(1)
    return [[str(d.date()), round(float(v), 2)] for d, v in s.tail(n).items()]


def build_context(data: dict, root: Path = config.CACHE) -> dict:
    br, us, prices = cache.load("macro_br", root), cache.load("macro_us", root), cache.load("prices", root)
    series: dict[str, dict] = {}

    def add(sid, label, unit, source, pts):
        if pts:
            series[sid] = {"label": label, "unit": unit, "source": source, "history": pts}

    if br is not None:
        for code, (key, label, unit, freq, _r) in config.SGS.items():
            add(key, label, unit, f"BCB SGS {code}", _points(br, key, "W-FRI" if freq == "daily" else None,
                                                              10 if freq == "daily" else 8))
        sel = br[br["series"] == "selic_target"].assign(date=lambda d: pd.to_datetime(d["date"])).set_index("date")["value"].resample("MS").last()
        ipca = br[br["series"] == "ipca_12m"].assign(date=lambda d: pd.to_datetime(d["date"])).set_index("date")["value"]
        real = (sel - ipca).dropna().tail(8)
        add("real_rate", "Real rate (Selic target - IPCA 12m), monthly", "pp", "computed from BCB SGS 432 and 13522",
            [[str(d.date()), round(float(v), 2)] for d, v in real.items()])
    if us is not None:
        for sid, (key, label, unit, freq, _r) in config.FRED.items():
            if key == "cpi_us":
                cpi = us[us["series"] == "cpi_us"].assign(date=lambda d: pd.to_datetime(d["date"])).set_index("date")["value"].dropna()
                yoy = (cpi.pct_change(12) * 100).dropna().tail(8)
                add("cpi_yoy", "US CPI y/y", "% 12m", "computed from FRED CPIAUCSL",
                    [[str(d.date()), round(float(v), 2)] for d, v in yoy.items()])
            else:
                add(key, label, unit, f"FRED {sid}", _points(us, key, "W-FRI" if freq == "daily" else None,
                                                              10 if freq == "daily" else 8))
        w = us.assign(date=lambda d: pd.to_datetime(d["date"])).pivot_table(index="date", columns="series", values="value")
        if {"ust_10y", "ust_2y"} <= set(w.columns):
            curve = (w["ust_10y"] - w["ust_2y"]).dropna().resample("W-FRI").last().dropna().tail(10)
            add("curve_10y2y", "US curve 10y - 2y", "pp", "computed from FRED DGS10 and DGS2",
                [[str(d.date()), round(float(v), 2)] for d, v in curve.items()])
    for f in data.get("macro", {}).get("focus", []):
        add(f"{f['key']}_{f['year']}", f"{f['label']} for {f['year']}, median", f["unit"], "BCB Focus survey",
            [[f"4 weeks earlier", f["median_4w_ago"]], [f["date"], f["median"]]])
    if prices is not None:
        for t in ("IBOV", "SPX", "USDBRL"):
            add(f"px_{t}", f"{config.TICKERS[t][2]} weekly close", "points" if t != "USDBRL" else "BRL per USD",
                "Yahoo Finance", _points(prices.rename(columns={"ticker": "series", "close": "value"}), t, "W-FRI", 10))
    for region, r in (data.get("risk") or {}).items():
        add(f"risk_{region}", f"{region} stocks, trailing 1-year risk ({r['window']})", "vol %, beta, max drawdown %, Sharpe",
            "computed from Yahoo Finance prices",
            [[x["ticker"], {"vol": x["vol"], "beta": x["beta"], "mdd": x["mdd"], "sharpe": x["sharpe"]}] for x in r["rows"]])
    add("alerts", "Rule-based alerts", "text", "computed", [[a["code"], a["text"]] for a in data.get("alerts", [])])
    return {"as_of": data.get("as_of"), "ipca_target": "3.0% with a 1.5 pp band (1.5% to 4.5%)", "series": series}


def schemas(context: dict) -> tuple[dict, dict]:
    ids = sorted(context["series"])
    api = {"type": "object", "additionalProperties": False, "required": ["answer", "series_used", "cannot_answer"],
           "properties": {"answer": {"type": "string"},
                          "series_used": {"type": "array", "items": {"type": "string", "enum": ids}},
                          "cannot_answer": {"type": "boolean"}}}
    strict = json.loads(json.dumps(api))
    strict["properties"]["answer"].update(minLength=10, maxLength=900)
    strict["properties"]["series_used"].update(maxItems=8)
    return api, strict


def _check(answer: dict, context: dict) -> list[str]:
    problems = number_check({"headline": answer.get("answer", "")}, context)
    if not answer.get("cannot_answer") and not answer.get("series_used"):
        problems.append("series_used is empty: cite the series the answer relies on")
    return problems


def ask_one(question: str, context: dict, llm: LLM) -> dict:
    question = question.strip()[:300]
    api, strict = schemas(context)
    prompt = f"Context (JSON):\n{json.dumps(context, ensure_ascii=False)}\n\nQuestion: {question}"
    answer, meta = llm.ask("ask", SYSTEM, prompt, api, strict, check=lambda a: _check(a, context))
    cited = [{"id": s, "label": context["series"][s]["label"], "source": context["series"][s]["source"]}
             for s in answer["series_used"]]
    meta = {k: meta.get(k) for k in ("mode", "recorded_at", "input_tokens", "output_tokens")}
    return {"question": question, "answer": answer["answer"], "cannot_answer": answer["cannot_answer"],
            "series_used": cited, "number_check": "passed", "meta": meta}


def run_presets(mode: str = "auto", today: date | None = None, out: Path = ASK_FILE, client=None,
                recordings: Path = config.RECORDINGS, cache_root: Path = config.CACHE) -> dict:
    """Answer the preset questions. If a question fails (no key, no recording, API down), keep its previous answer."""
    data = analytics.json_safe(analytics.payload(today, cache_root))
    context = build_context(data, cache_root)
    llm = LLM(mode=mode, client=client, recordings=recordings, max_calls=config.ASK_MAX_CALLS)
    previous = {i["question"]: i for i in json.loads(out.read_text(encoding="utf-8"))["items"]} if out.exists() else {}
    items = []
    for q in PRESETS:
        try:
            items.append({**ask_one(q, context, llm), "as_of": data.get("as_of")})
        except Exception as e:  # noqa: BLE001
            if q in previous:
                items.append({**previous[q], "stale_reason": f"{type(e).__name__}"})
            print(f"ask: '{q[:40]}...' not refreshed ({type(e).__name__}: {str(e)[:120]})")
    result = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": config.MODEL,
              "api_calls": llm.calls, "input_tokens": llm.tokens_in, "output_tokens": llm.tokens_out,
              "cost_usd": round(llm.cost_usd(), 6), "items": items}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"ask: {len(items)} answers · api calls {llm.calls} · {llm.tokens_in} in / {llm.tokens_out} out tokens "
          f"· ~US$ {llm.cost_usd():.5f}")
    return result


def ask_live(question: str, cache_root: Path = config.CACHE, client=None, mode: str = "auto") -> dict:
    data = analytics.json_safe(analytics.payload(None, cache_root))
    # live questions are cached outside the repository (they are whatever someone typed)
    llm = LLM(mode=mode, client=client, max_calls=config.MAX_CALLS_PER_RUN, recordings=config.ROOT / ".live-answers")
    res = ask_one(question, build_context(data, cache_root), llm)
    res["meta"].update(api_calls=llm.calls, cost_usd=round(llm.cost_usd(), 6))
    return res
