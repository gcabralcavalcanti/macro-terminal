"""Shared fixtures. Nothing here touches the network: data is either recorded (tests/fixtures/) or synthetic."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from macro_terminal import cache, config

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 19)


@pytest.fixture
def today():
    return TODAY


def _series(key, start, periods, freq, base, step=0.0, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=periods, freq=freq)
    vals = base + step * np.arange(periods) + rng.normal(0, 0.01, periods)
    return pd.DataFrame({"date": idx, "series": key, "value": vals.round(4)})


@pytest.fixture
def cache_dir(tmp_path) -> Path:
    """A complete synthetic cache, shaped exactly like the real one."""
    root = tmp_path / "cache"
    br = pd.concat(
        [
            _series("selic_target", "2024-01-01", 650, "B", 13.75),
            _series("usdbrl_ptax", "2024-01-01", 650, "B", 5.2, seed=1),
            _series("ipca_12m", "2024-01-01", 33, "MS", 4.5),
            _series("ipca_mom", "2024-01-01", 33, "MS", 0.3),
            _series("unemployment_br", "2024-01-01", 32, "MS", 6.0),
        ]
    )
    us = pd.concat(
        [
            _series("fed_funds", "2024-01-01", 650, "B", 4.0),
            _series("ust_2y", "2024-01-01", 650, "B", 4.2),
            _series("ust_10y", "2024-01-01", 650, "B", 4.5),
            _series("cpi_us", "2024-01-01", 33, "MS", 300, step=0.8),
            _series("unemployment_us", "2024-01-01", 33, "MS", 4.2),
        ]
    )
    focus = pd.DataFrame(
        [
            {"date": d, "series": k, "ref_year": y, "value": v + (0.1 if d == "2026-10-16" else 0), "respondents": 100}
            for d in ("2026-09-18", "2026-10-16")
            for k, v in (("focus_ipca", 5.0), ("focus_selic", 13.5), ("focus_fx", 5.2), ("focus_gdp", 1.9))
            for y in (2026, 2027)
        ]
    )
    rng = np.random.default_rng(42)
    days = pd.bdate_range(end="2026-10-19", periods=300)
    market = rng.normal(0, 0.01, len(days))
    rows = []
    for i, t in enumerate(config.TICKERS):
        beta = 1.0 if t in ("IBOV", "SPX") else 0.5 + i * 0.05
        r = beta * market + (0 if t in ("IBOV", "SPX") else rng.normal(0, 0.01, len(days)))
        close = 100 * np.cumprod(1 + r)
        rows.append(
            pd.DataFrame(
                {
                    "date": days,
                    "ticker": t,
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "volume": rng.integers(1e5, 1e6, len(days)),
                }
            )
        )
    prices = pd.concat(rows)
    fund = pd.DataFrame(
        [
            {"ticker": t, "period": p, "period_end": e, "metric": m, "value": v}
            for t in ("PETR4", "VALE3")
            for p, e in (("2026Q1", "2026-03-31"), ("2026Q2", "2026-06-30"))
            for m, v in (("revenue", 1.2e8), ("gross_profit", 5e7), ("ebit", 3e7), ("net_income", 2e7))
        ]
    )
    filings = pd.DataFrame(
        [
            {
                "date": "2026-10-16",
                "ticker": "PETR4",
                "category": "FR",
                "category_en": "Material fact",
                "subject": "Board approves dividends",
                "link": "https://www.rad.cvm.gov.br/x",
            }
        ]
    )
    for name, df, col in (
        ("macro_br", br, "date"),
        ("macro_us", us, "date"),
        ("focus", focus, "date"),
        ("prices", prices, "date"),
        ("fundamentals", fund, "period_end"),
        ("filings", filings, "date"),
    ):
        cache.save(name, df, "synthetic", [], root=root, date_col=col)
    return root


class FakeClient:
    """Stands in for anthropic.Anthropic: returns queued answers, counts calls."""

    def __init__(self, answers: list[dict]):
        self.answers = list(answers)
        self.calls = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls += 1
        self.last_request = kw
        answer = self.answers.pop(0)
        return SimpleNamespace(
            usage=SimpleNamespace(input_tokens=1000, output_tokens=200),
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=json.dumps(answer))],
        )


@pytest.fixture
def fake_client():
    return FakeClient


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any accidental HTTP call fails the test."""

    def blocked(*a, **k):
        raise AssertionError("network access in a test")

    monkeypatch.setattr("macro_terminal.net.requests.get", blocked)
