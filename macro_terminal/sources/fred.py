"""FRED (Federal Reserve Bank of St. Louis) via the public CSV endpoint: no API key needed."""
from __future__ import annotations

import io
from datetime import date

import pandas as pd

from .. import config, net

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def parse_csv(text: str, key: str) -> pd.DataFrame:
    """CSV with two columns: observation_date, <SERIES>. Missing values come as '.' or empty."""
    raw = pd.read_csv(io.StringIO(text))
    if raw.shape[1] != 2:
        raise ValueError(f"{key}: unexpected FRED layout {list(raw.columns)}")
    raw.columns = ["date", "value"]
    return pd.DataFrame({"date": pd.to_datetime(raw["date"], errors="coerce"), "series": key,
                         "value": pd.to_numeric(raw["value"], errors="coerce")})


def fetch(today: date) -> pd.DataFrame:
    parts = []
    for sid, (key, *_rest) in config.FRED.items():
        text = net.get(URL, params={"id": sid, "cosd": config.FRED_START}).text
        df = parse_csv(text, key)
        # FRED marks holidays as missing ('.'); they are not data gaps
        parts.append(df.dropna(subset=["value"]) if sid.startswith(("DFF", "DGS")) else df)
    return pd.concat(parts, ignore_index=True)


def spec() -> dict:
    return {key: (label, unit, freq, rng) for key, label, unit, freq, rng in config.FRED.values()}
