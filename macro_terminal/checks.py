"""Automatic data checks: missing values, dates and units.

Every check returns issues as {"level": "error" | "warn", "msg": ...}.
- error: the new download is rejected and the last good cache is kept (the page marks it STALE).
- warn: the data is used, and the warning is shown on the STATUS tab.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

# how old the last observation may be before it is flagged (days)
MAX_AGE = {"daily": 10, "weekly": 21, "monthly": 100, "quarterly": 200}
MAX_MISSING_SHARE = 0.20
MAX_DAILY_MOVE = 0.40   # |return| above 40% in one day is flagged (split, bad tick, wrong unit)


def _issue(level: str, msg: str) -> dict:
    return {"level": level, "msg": msg}


def has_errors(issues: list[dict]) -> bool:
    return any(i["level"] == "error" for i in issues)


def _base(df: pd.DataFrame, required: list[str], name: str) -> list[dict]:
    if df is None or df.empty:
        return [_issue("error", f"{name}: no rows returned")]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        return [_issue("error", f"{name}: missing columns {missing_cols}")]
    return []


def check_series(df: pd.DataFrame, spec: dict, today: date, name: str):
    """df columns: date, series, value. spec: key -> (label, unit, frequency, (lo, hi)).
    Returns (clean_df, issues)."""
    issues = _base(df, ["date", "series", "value"], name)
    if issues:
        return df, issues
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    bad_dates = int(df["date"].isna().sum())
    if bad_dates:
        issues.append(_issue("warn", f"{name}: {bad_dates} rows with unreadable dates dropped"))
        df = df.dropna(subset=["date"])
    future = df["date"].dt.date > today
    if future.any():
        # e.g. the Selic target series is published up to the next policy meeting
        issues.append(_issue("warn", f"{name}: {int(future.sum())} observations dated after today dropped"))
        df = df[~future]
    keys = ["series", "date"] + (["ref_year"] if "ref_year" in df.columns else [])
    dup = df.duplicated(keys, keep="last")
    if dup.any():
        issues.append(_issue("warn", f"{name}: {int(dup.sum())} duplicated dates dropped"))
        df = df[~dup]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    for key, (label, unit, freq, (lo, hi)) in spec.items():
        s = df[df["series"] == key]
        if s.empty:
            issues.append(_issue("error", f"{label}: series missing from the download"))
            continue
        share = s["value"].isna().mean()
        if share > MAX_MISSING_SHARE:
            issues.append(_issue("error", f"{label}: {share:.0%} of values missing"))
        elif share > 0:
            issues.append(_issue("warn", f"{label}: {int(s['value'].isna().sum())} missing values dropped"))
        v = s["value"].dropna()
        out = v[(v < lo) | (v > hi)]
        if not out.empty:
            issues.append(_issue("error", f"{label}: {len(out)} values outside the plausible range "
                                          f"[{lo}, {hi}] {unit} (unit change?), e.g. {out.iloc[-1]}"))
        age = (pd.Timestamp(today) - s["date"].max()).days
        if age > MAX_AGE[freq]:
            issues.append(_issue("warn", f"{label}: last observation is {age} days old "
                                         f"({s['date'].max().date()})"))
    df = df.dropna(subset=["value"]).sort_values(["series", "date"]).reset_index(drop=True)
    return df, issues


def check_prices(df: pd.DataFrame, expected: list[str], today: date, name: str = "prices"):
    """df columns: date, ticker, open, high, low, close, volume."""
    issues = _base(df, ["date", "ticker", "close", "volume"], name)
    if issues:
        return df, issues
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "close"])
    df = df[df["date"].dt.date <= today]
    missing = sorted(set(expected) - set(df["ticker"]))
    if missing:
        issues.append(_issue("warn", f"{name}: no data for {', '.join(missing)}"))
    if (df["close"] <= 0).any():
        issues.append(_issue("error", f"{name}: non-positive close prices"))
    if (df["volume"].fillna(0) < 0).any():
        issues.append(_issue("error", f"{name}: negative volume"))
    if {"high", "low"} <= set(df.columns):
        inverted = (df["high"] < df["low"]).sum()
        if inverted:
            issues.append(_issue("warn", f"{name}: {int(inverted)} bars with high < low"))
    for t, g in df.sort_values("date").groupby("ticker"):
        r = g["close"].pct_change().abs()
        jumps = g.loc[r > MAX_DAILY_MOVE, "date"]
        if not jumps.empty:
            issues.append(_issue("warn", f"{t}: daily move above {MAX_DAILY_MOVE:.0%} on "
                                         f"{jumps.iloc[-1].date()} (split or bad tick?)"))
        age = (pd.Timestamp(today) - g["date"].max()).days
        if age > MAX_AGE["daily"]:
            issues.append(_issue("warn", f"{t}: last price is {age} days old"))
    return df.sort_values(["ticker", "date"]).reset_index(drop=True), issues


def check_fundamentals(df: pd.DataFrame, name: str = "fundamentals"):
    """df columns: ticker, period, period_end, metric, value (BRL thousands)."""
    issues = _base(df, ["ticker", "period", "metric", "value"], name)
    if issues:
        return df, issues
    rev = df[df["metric"] == "revenue"]
    if rev.empty:
        return df, [_issue("error", f"{name}: no revenue lines")]
    # Unit check: CVM values are converted to BRL thousands. A large listed company's quarterly
    # revenue sits between BRL 100 million and BRL 1 trillion; anything else means a scale error.
    off = rev[(rev["value"] < 1e5) | (rev["value"] > 1e9)]
    if not off.empty:
        issues.append(_issue("error", f"{name}: revenue outside BRL 100 mn - 1 tn per quarter for "
                                      f"{sorted(off['ticker'].unique())} (scale error?)"))
    counts = df[df["metric"] == "revenue"].groupby("ticker").size()
    short = counts[counts < 4]
    for t, n in short.items():
        issues.append(_issue("warn", f"{t}: only {n} quarters of fundamentals"))
    return df, issues


def check_filings(df: pd.DataFrame, today: date, name: str = "filings"):
    issues = _base(df, ["date", "ticker", "category", "link"], name)
    if issues:
        return df, issues
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    bad = df["date"].isna() | (df["date"].dt.date > today)
    if bad.any():
        issues.append(_issue("warn", f"{name}: {int(bad.sum())} rows with missing or future dates dropped"))
        df = df[~bad]
    nolink = ~df["link"].astype(str).str.startswith("http")
    if nolink.any():
        issues.append(_issue("warn", f"{name}: {int(nolink.sum())} filings without a download link"))
    return df, issues
