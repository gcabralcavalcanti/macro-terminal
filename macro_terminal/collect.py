"""Download -> checks -> cache. A failing source keeps its last good copy and is marked stale."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from datetime import date

import pandas as pd

from . import cache, checks, config
from .sources import bcb, cvm, fred, market

SOURCES = {
    "macro_br": "BCB SGS (api.bcb.gov.br)",
    "focus": "BCB Focus survey (olinda.bcb.gov.br)",
    "macro_us": "FRED (fred.stlouisfed.org, public CSV)",
    "prices": "Yahoo Finance (yfinance, unofficial)",
    "fundamentals": "CVM open data, ITR/DFP (dados.cvm.gov.br)",
    "filings": "CVM open data, IPE (dados.cvm.gov.br)",
}


def run_one(
    name: str,
    fetch: Callable[[], pd.DataFrame],
    check: Callable[[pd.DataFrame], tuple[pd.DataFrame, list[dict]]],
    date_col: str | None = "date",
    root=config.CACHE,
) -> str:
    source = SOURCES[name]
    try:
        df = fetch()
    except Exception as e:  # noqa: BLE001  any source failure falls back to the cache
        cache.mark_failed(name, source, f"{type(e).__name__}: {e}", root=root)
        print(f"  {name}: FETCH FAILED, keeping cache ({e})")
        traceback.print_exc(limit=1)
        return "stale"
    clean, issues = check(df)
    if checks.has_errors(issues):
        cache.mark_failed(name, source, "rejected by checks", issues, root=root)
        print(f"  {name}: REJECTED by checks, keeping cache: {[i['msg'] for i in issues if i['level'] == 'error']}")
        return "stale"
    cache.save(name, clean, source, issues, root=root, date_col=date_col)
    print(f"  {name}: ok, {len(clean)} rows, {len(issues)} warnings")
    return "live"


def collect(today: date | None = None, only: list[str] | None = None, root=config.CACHE) -> dict:
    today = today or date.today()
    expected = list(config.TICKERS)

    def prices_fetch():
        new = market.fetch()
        filled, missing = market.fill_from_cache(new, cache.load("prices", root))
        if missing:
            print(f"  prices: {missing} not returned today, kept from cache")
        return filled

    jobs = {
        "macro_br": (
            lambda: bcb.fetch_sgs(today),
            lambda d: checks.check_series(d, bcb.sgs_spec(), today, "BCB SGS"),
            "date",
        ),
        "focus": (
            lambda: bcb.fetch_focus(today),
            lambda d: checks.check_series(d, bcb.focus_spec(), today, "Focus"),
            "date",
        ),
        "macro_us": (lambda: fred.fetch(today), lambda d: checks.check_series(d, fred.spec(), today, "FRED"), "date"),
        "prices": (prices_fetch, lambda d: checks.check_prices(d, expected, today), "date"),
        "fundamentals": (lambda: cvm.fetch_fundamentals(today), checks.check_fundamentals, "period_end"),
        "filings": (lambda: cvm.fetch_filings(today), lambda d: checks.check_filings(d, today), "date"),
    }
    result = {}
    for name, (fetch, check, date_col) in jobs.items():
        if only and name not in only:
            continue
        print(f"collect {name}")
        result[name] = run_one(name, fetch, check, date_col, root)
    return result
