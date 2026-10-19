"""Numbers shown on the page, computed from the cache only (no network).

Risk metrics use the last 252 trading days of daily simple returns:
- volatility: annualised standard deviation (x sqrt 252)
- beta: cov(stock, benchmark) / var(benchmark); Ibovespa for Brazil, S&P 500 for the US
- max drawdown: worst fall from a running peak of the close
- Sharpe: (annualised mean return - risk-free) / volatility; risk-free = average Selic target (BR)
  or effective fed funds (US) over the same window
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from . import cache, config

WINDOW = 252
CHART_DAYS = 260


def _r(x, nd=2):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), nd)


# ---------------------------------------------------------------- macro
def _series_block(df: pd.DataFrame, key: str, label: str, unit: str, spark_n: int = 24) -> dict | None:
    s = df[df["series"] == key].sort_values("date")
    if s.empty:
        return None
    last, prev = s.iloc[-1], (s.iloc[-2] if len(s) > 1 else s.iloc[-1])
    return {"key": key, "label": label, "unit": unit, "last": _r(last["value"]), "date": str(last["date"].date()),
            "prev": _r(prev["value"]), "chg": _r(last["value"] - prev["value"]),
            "spark": [_r(v) for v in s["value"].tail(spark_n)]}


def _monthly(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """Daily series -> month-end values, so sparklines of daily and monthly series look alike."""
    s = df[df["series"] == key].set_index("date")["value"].resample("ME").last().dropna()
    return s.reset_index().assign(series=key)


def macro(br: pd.DataFrame | None, us: pd.DataFrame | None, focus: pd.DataFrame | None, today: date) -> dict:
    out = {"br": [], "us": [], "focus": []}
    if br is not None and not br.empty:
        br = br.assign(date=pd.to_datetime(br["date"]))
        for code, (key, label, unit, freq, _rng) in config.SGS.items():
            src = pd.concat([_monthly(br, key).iloc[:-1], br[br["series"] == key].tail(1)]) if freq == "daily" else br
            b = _series_block(src, key, label, unit)
            if b:
                b["source"] = f"BCB SGS {code}"
                out["br"].append(b)
        sel = br[br["series"] == "selic_target"]["value"]
        ipca = br[br["series"] == "ipca_12m"]["value"]
        if len(sel) and len(ipca):
            out["br"].append({"key": "real_rate", "label": "Real rate (Selic - IPCA 12m)", "unit": "pp",
                              "last": _r(sel.iloc[-1] - ipca.iloc[-1]), "date": str(br["date"].max().date()),
                              "prev": None, "chg": None, "spark": [], "source": "computed"})
    if us is not None and not us.empty:
        us = us.assign(date=pd.to_datetime(us["date"]))
        for sid, (key, label, unit, freq, _rng) in config.FRED.items():
            if key == "cpi_us":
                cpi = us[us["series"] == "cpi_us"].set_index("date")["value"].dropna()
                yoy = (cpi.pct_change(12) * 100).dropna().reset_index().assign(series="cpi_yoy")
                b = _series_block(yoy, "cpi_yoy", "CPI y/y", "% 12m")
            else:
                src = pd.concat([_monthly(us, key).iloc[:-1], us[us["series"] == key].tail(1)]) if freq == "daily" else us
                b = _series_block(src, key, label, unit)
            if b:
                b["source"] = f"FRED {sid}"
                out["us"].append(b)
        y2 = us[us["series"] == "ust_2y"].set_index("date")["value"]
        y10 = us[us["series"] == "ust_10y"].set_index("date")["value"]
        spread = (y10 - y2).dropna()
        if len(spread):
            out["us"].append({"key": "curve_10y2y", "label": "Curve 10y - 2y", "unit": "pp",
                              "last": _r(spread.iloc[-1]), "date": str(spread.index[-1].date()),
                              "prev": None, "chg": None, "spark": [], "source": "computed"})
    if focus is not None and not focus.empty:
        f = focus.assign(date=pd.to_datetime(focus["date"]))
        latest = f["date"].max()
        ago = f[f["date"] <= latest - pd.Timedelta(days=28)]["date"].max()
        for key, label, unit, _rng in config.FOCUS.values():
            for year in (today.year, today.year + 1):
                cur = f[(f["series"] == key) & (f["ref_year"] == year) & (f["date"] == latest)]
                old = f[(f["series"] == key) & (f["ref_year"] == year) & (f["date"] == ago)]
                if cur.empty:
                    continue
                v = cur["value"].iloc[0]
                o = old["value"].iloc[0] if not old.empty else None
                out["focus"].append({"key": key, "label": label, "unit": unit, "year": int(year),
                                     "median": _r(v), "median_4w_ago": _r(o),
                                     "chg_4w": _r(v - o) if o is not None else None,
                                     "respondents": int(cur["respondents"].iloc[0]) if not pd.isna(cur["respondents"].iloc[0]) else None,
                                     "date": str(latest.date())})
    return out


# ---------------------------------------------------------------- market
def watchlist(prices: pd.DataFrame) -> list[dict]:
    rows = []
    last_by_region: dict[str, pd.Timestamp] = {}
    for t, (_sym, region, name, _code) in config.TICKERS.items():
        g = prices[prices["ticker"] == t]
        if not g.empty:
            last_by_region[region] = max(last_by_region.get(region, g["date"].max()), g["date"].max())
    for t, (_sym, region, name, _code) in config.TICKERS.items():
        g = prices[prices["ticker"] == t].sort_values("date")
        if g.empty:
            rows.append({"ticker": t, "name": name, "region": region, "last": None, "chg_pct": None,
                         "date": None, "stale": True})
            continue
        last, prev = g.iloc[-1], (g.iloc[-2] if len(g) > 1 else g.iloc[-1])
        rows.append({"ticker": t, "name": name, "region": region, "last": _r(last["close"]),
                     "chg": _r(last["close"] - prev["close"]),
                     "chg_pct": _r((last["close"] / prev["close"] - 1) * 100),
                     "date": str(last["date"].date()),
                     "stale": bool(last["date"] < last_by_region[region] - pd.Timedelta(days=3))})
    return rows


def charts(prices: pd.DataFrame) -> dict:
    out = {}
    for t, g in prices.sort_values("date").groupby("ticker"):
        c = g.set_index("date")["close"]
        ma = {n: c.rolling(n).mean() for n in (20, 50, 200)}
        tail = g.tail(CHART_DAYS)
        idx = tail["date"]
        hi52 = c.tail(WINDOW).max()
        lo52 = c.tail(WINDOW).min()
        out[t] = {"dates": [str(d.date()) for d in idx],
                  "close": [_r(v) for v in tail["close"]],
                  "ma20": [_r(ma[20].get(d)) for d in idx],
                  "ma50": [_r(ma[50].get(d)) for d in idx],
                  "ma200": [_r(ma[200].get(d)) for d in idx],
                  "volume": [int(v) if not pd.isna(v) else 0 for v in tail["volume"]],
                  "hi52": _r(hi52), "lo52": _r(lo52),
                  "avg_vol_20": int(g["volume"].tail(20).mean()) if g["volume"].notna().any() else 0}
    return out


def _avg_rate(macro_df: pd.DataFrame | None, key: str, start: pd.Timestamp) -> float | None:
    if macro_df is None or macro_df.empty:
        return None
    s = macro_df[(macro_df["series"] == key) & (pd.to_datetime(macro_df["date"]) >= start)]["value"]
    return float(s.mean()) if len(s) else None


def risk(prices: pd.DataFrame, br: pd.DataFrame | None, us: pd.DataFrame | None) -> dict:
    wide = prices.pivot_table(index="date", columns="ticker", values="close").sort_index()
    out = {}
    for region, bench in config.BENCHMARK.items():
        members = [t for t, v in config.TICKERS.items() if v[1] == region]
        cols = [c for c in members + [bench] + (["USDBRL"] if region == "BR" else []) if c in wide]
        w = wide[cols].dropna(how="all")
        # each market on its own calendar: keep days when the benchmark traded
        w = w[w[bench].notna()].tail(WINDOW + 1) if bench in w else w.tail(WINDOW + 1)
        rets = w.pct_change(fill_method=None).iloc[1:]
        start = rets.index.min()
        rf = _avg_rate(br, "selic_target", start) if region == "BR" else _avg_rate(us, "fed_funds", start)
        rows = []
        for t in members:
            if t not in rets:
                continue
            r = rets[t].dropna()
            if len(r) < 60:
                continue
            vol = r.std() * math.sqrt(252)
            pair = rets[[t, bench]].dropna() if bench in rets else None
            beta = (pair[t].cov(pair[bench]) / pair[bench].var()) if pair is not None and len(pair) > 60 else None
            path = w[t].dropna()
            mdd = (path / path.cummax() - 1).min()
            ann = r.mean() * 252
            sharpe = (ann - (rf or 0) / 100) / vol if vol else None
            rows.append({"ticker": t, "vol": _r(vol * 100), "beta": _r(beta), "mdd": _r(mdd * 100),
                         "sharpe": _r(sharpe), "ret_1y": _r((path.iloc[-1] / path.iloc[0] - 1) * 100),
                         "obs": int(len(r))})
        corr = rets[cols].corr(min_periods=60)
        out[region] = {"benchmark": bench, "rf": _r(rf), "rf_label": "avg Selic target" if region == "BR"
                       else "avg effective fed funds", "window": f"{start.date()} to {rets.index.max().date()}",
                       "rows": rows, "corr": {"tickers": cols,
                                              "matrix": [[_r(corr.loc[a, b]) for b in cols] for a in cols]}}
    return out


# ---------------------------------------------------------------- fundamentals and filings
def fundamentals(df: pd.DataFrame | None) -> dict:
    if df is None or df.empty:
        return {}
    out = {}
    for t, g in df.groupby("ticker"):
        w = g.pivot_table(index="metric", columns="period", values="value")
        periods = sorted(w.columns)
        rows = {m: [_r(w.loc[m, p] / 1000, 1) if m in w.index and not pd.isna(w.loc[m, p]) else None for p in periods]
                for m in ("revenue", "gross_profit", "ebit", "net_income")}  # BRL thousands -> BRL millions
        for name, num in (("gross_margin", "gross_profit"), ("ebit_margin", "ebit"), ("net_margin", "net_income")):
            rows[name] = [_r(n / d * 100, 1) if n is not None and d else None for n, d in zip(rows[num], rows["revenue"])]
        out[t] = {"periods": periods, "rows": rows, "unit": "BRL mn"}
    return out


def filings(df: pd.DataFrame | None) -> list[dict]:
    if df is None or df.empty:
        return []
    df = df.assign(date=pd.to_datetime(df["date"])).sort_values("date", ascending=False)
    return [{"date": str(r.date.date()), "ticker": r.ticker, "category": r.category, "category_en": r.category_en,
             "subject": str(r.subject) if not pd.isna(r.subject) else "", "link": r.link} for r in df.itertuples()]


# ---------------------------------------------------------------- everything
def payload(today: date | None = None, root=config.CACHE) -> dict:
    today = today or date.today()
    br, us, foc = cache.load("macro_br", root), cache.load("macro_us", root), cache.load("focus", root)
    prices = cache.load("prices", root)
    data = {"macro": macro(br, us, foc, today), "status": cache.read_status(root)}
    if prices is not None and not prices.empty:
        prices = prices.assign(date=pd.to_datetime(prices["date"]))
        data["watchlist"] = watchlist(prices)
        data["charts"] = charts(prices)
        data["risk"] = risk(prices, br, us)
        data["as_of"] = str(prices["date"].max().date())
    else:
        data.update(watchlist=[], charts={}, risk={}, as_of=None)
    data["fundamentals"] = fundamentals(cache.load("fundamentals", root))
    data["filings"] = filings(cache.load("filings", root))
    data["names"] = {t: v[2] for t, v in config.TICKERS.items()}
    data["no_fundamentals"] = sorted(config.NO_FUNDAMENTALS)
    return data


def json_safe(obj):
    """Replace NaN/inf (not valid JSON) with None, recursively."""
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return json_safe(float(obj))
    return obj
