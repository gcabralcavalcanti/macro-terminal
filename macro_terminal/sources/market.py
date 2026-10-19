"""Daily prices from Yahoo Finance (unofficial). Tickers missing from a download keep their cached history."""

from __future__ import annotations

import pandas as pd

from .. import config


def tidy(raw: pd.DataFrame, symbol_to_ticker: dict[str, str]) -> pd.DataFrame:
    """yfinance multi-ticker frame (columns: field x symbol) -> long table."""
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume"])
    stacked = raw.stack(level=1, future_stack=True).reset_index()
    stacked.columns = [str(c).lower() for c in stacked.columns]
    stacked = stacked.rename(columns={stacked.columns[0]: "date", stacked.columns[1]: "symbol"})
    stacked["ticker"] = stacked["symbol"].map(symbol_to_ticker)
    out = stacked.dropna(subset=["ticker", "close"])[["date", "ticker", "open", "high", "low", "close", "volume"]]
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None).dt.normalize()
    return out.reset_index(drop=True)


def fetch() -> pd.DataFrame:
    import yfinance as yf  # imported here so tests and the page build never need it

    symbols = {v[0]: k for k, v in config.TICKERS.items()}
    raw = yf.download(
        list(symbols),
        period=config.PRICE_PERIOD,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    return tidy(raw, symbols)


def fill_from_cache(new: pd.DataFrame, old: pd.DataFrame | None) -> tuple[pd.DataFrame, list[str]]:
    """Tickers missing from today's download keep their cached history."""
    if old is None or old.empty:
        return new, []
    missing = sorted(set(old["ticker"]) - set(new["ticker"]))
    if not missing:
        return new, []
    keep = old[old["ticker"].isin(missing)].copy()
    keep["date"] = pd.to_datetime(keep["date"])
    return pd.concat([new, keep], ignore_index=True), missing
