"""Rule-based alerts shown in the top bar. Plain code, no AI: every alert says which rule fired and on what number."""
from __future__ import annotations

from datetime import date

import pandas as pd


# Brazil's inflation target (CMN): continuous 3.0% with a 1.5 pp tolerance band, in force since 2025.
IPCA_TARGET, IPCA_BAND = 3.0, 1.5
FX_MOVE_PCT = 2.0        # USD/BRL daily move that raises an alert
INDEX_MOVE_PCT = 2.0     # Ibovespa / S&P 500
STOCK_MOVE_PCT = 5.0     # single stocks
POLICY_LOOKBACK_DAYS = 45  # a policy-rate change stays on the bar this long


def _alert(level: str, code: str, text: str, rule: str) -> dict:
    return {"level": level, "code": code, "text": text, "rule": rule}


def _last_change(df: pd.DataFrame, key: str, min_step: float) -> tuple[pd.Timestamp, float, float] | None:
    """Last day the series moved by at least min_step from the day before."""
    s = df[df["series"] == key].sort_values("date").reset_index(drop=True)
    step = s["value"].diff()
    hits = s.index[step.abs() >= min_step]
    if len(hits) == 0:
        return None
    i = hits[-1]
    return s.loc[i, "date"], float(s.loc[i - 1, "value"]), float(s.loc[i, "value"])


def policy_rates(br: pd.DataFrame | None, us: pd.DataFrame | None, today: date) -> list[dict]:
    out = []
    # the effective fed funds rate drifts by 1-2 bp; a policy move is 20 bp or more
    for df, key, name, step in ((br, "selic_target", "Selic target", 0.01), (us, "fed_funds", "Fed funds", 0.20)):
        if df is None or df.empty:
            continue
        df = df.assign(date=pd.to_datetime(df["date"]))
        ch = _last_change(df, key, step)
        if ch and (pd.Timestamp(today) - ch[0]).days <= POLICY_LOOKBACK_DAYS:
            d, old, new = ch
            bp = round((new - old) * 100)
            verb = "cut" if bp < 0 else "hike"
            out.append(_alert("info", "RATE", f"{name} {verb} {abs(bp)} bp to {new:.2f}% on {d.date()}",
                              f"policy rate changed in the last {POLICY_LOOKBACK_DAYS} days"))
    return out


def inflation(macro: dict) -> list[dict]:
    out = []
    hi, lo = IPCA_TARGET + IPCA_BAND, IPCA_TARGET - IPCA_BAND
    for r in macro.get("br", []):
        if r["key"] == "ipca_12m" and r["last"] is not None and not lo <= r["last"] <= hi:
            side = "above the ceiling" if r["last"] > hi else "below the floor"
            out.append(_alert("warn", "IPCA", f"IPCA 12m {r['last']:.2f}% {side} of the {lo:.1f}-{hi:.1f}% target band ({r['date'][:7]})",
                              f"IPCA 12m outside {IPCA_TARGET} +/- {IPCA_BAND}"))
    for f in macro.get("focus", []):
        if f["key"] == "focus_ipca" and f["median"] is not None and f["median"] > hi:
            out.append(_alert("warn", "FOCUS", f"Focus IPCA {f['year']} at {f['median']:.2f}%, above the {hi:.1f}% ceiling",
                              "market inflation expectation above the band"))
    return out


def market_moves(watchlist: list[dict]) -> list[dict]:
    out = []
    for w in watchlist:
        c = w.get("chg_pct")
        if c is None:
            continue
        limit = {"FX": FX_MOVE_PCT, "IDX": INDEX_MOVE_PCT}.get(w["region"], STOCK_MOVE_PCT)
        if abs(c) >= limit:
            out.append(_alert("warn" if w["region"] in ("FX", "IDX") else "info", "MOVE",
                              f"{w['ticker']} {c:+.2f}% on {w['date']}", f"daily move of {limit:.0f}% or more"))
    return out


def stale_data(status: dict) -> list[dict]:
    return [_alert("warn", "DATA", f"{k} is {s['status']}: showing the copy from {str(s.get('fetched_at') or 'never')[:10]}",
                   "a source failed or was rejected by the checks") for k, s in status.items() if s.get("status") != "live"]


def evaluate(data: dict, br: pd.DataFrame | None, us: pd.DataFrame | None, today: date) -> list[dict]:
    alerts = (policy_rates(br, us, today) + inflation(data.get("macro", {})) + market_moves(data.get("watchlist", []))
              + stale_data(data.get("status", {})))
    order = {"warn": 0, "info": 1}
    return sorted(alerts, key=lambda a: order[a["level"]])


RULES = [
    f"Policy rate (Selic target, fed funds) changed in the last {POLICY_LOOKBACK_DAYS} days",
    f"IPCA 12m outside the {IPCA_TARGET - IPCA_BAND:.1f}-{IPCA_TARGET + IPCA_BAND:.1f}% target band; Focus IPCA above the ceiling",
    f"USD/BRL or an index moved {FX_MOVE_PCT:.0f}% or more in a day; a stock moved {STOCK_MOVE_PCT:.0f}% or more",
    "A data source is stale or missing",
]
