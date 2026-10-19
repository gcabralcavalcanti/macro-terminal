"""Alerts, ASK and the newsletter, with the synthetic cache and the fake API client (no network, no cost)."""

import json

import pandas as pd

from macro_terminal import alerts, analytics, build
from macro_terminal.ask import ask_one, build_context, run_presets, schemas
from macro_terminal.brief import numbers_in
from macro_terminal.llm import LLM
from macro_terminal.newsletter import editions, line_svg, write_newsletter


# ---------------------------------------------------------------- alerts
def test_policy_rate_change_and_drift(today):
    days = pd.bdate_range(end="2026-10-16", periods=40)
    selic = pd.DataFrame({"date": days, "series": "selic_target", "value": [14.0] * 20 + [13.75] * 20})
    fed = pd.DataFrame({"date": days, "series": "fed_funds", "value": [3.63, 3.64] * 20})  # 1 bp drift only
    out = alerts.policy_rates(selic, fed, today)
    assert len(out) == 1 and "cut 25 bp to 13.75%" in out[0]["text"]


def test_inflation_band_and_moves():
    macro = {
        "br": [{"key": "ipca_12m", "last": 4.58, "date": "2026-09-01"}],
        "focus": [
            {"key": "focus_ipca", "year": 2026, "median": 5.22},
            {"key": "focus_ipca", "year": 2027, "median": 4.32},
        ],
    }
    out = alerts.inflation(macro)
    assert [a["code"] for a in out] == ["IPCA", "FOCUS"] and "2026" in out[1]["text"]
    wl = [
        {"ticker": "USDBRL", "region": "FX", "chg_pct": -2.1, "date": "d"},
        {"ticker": "PETR4", "region": "BR", "chg_pct": -2.8, "date": "d"},
        {"ticker": "NVDA", "region": "US", "chg_pct": 6.0, "date": "d"},
    ]
    assert [a["text"].split()[0] for a in alerts.market_moves(wl)] == ["USDBRL", "NVDA"]


def test_alerts_in_payload(cache_dir, today):
    data = analytics.payload(today, cache_dir)
    assert isinstance(data["alerts"], list) and data["alert_rules"]


# ---------------------------------------------------------------- ask
def test_context_and_closed_list_of_series(cache_dir, today):
    data = analytics.json_safe(analytics.payload(today, cache_dir))
    ctx = build_context(data, cache_dir)
    assert {"selic_target", "real_rate", "curve_10y2y", "px_IBOV", "risk_BR"} <= set(ctx["series"])
    weekly = ctx["series"]["selic_target"]["history"]
    assert all(d <= "2026-10-19" for d, _ in weekly)  # real dates, never an end-of-week label in the future
    api, strict = schemas(ctx)
    assert api["properties"]["series_used"]["items"]["enum"] == sorted(ctx["series"])


def test_ask_rejects_invented_number_then_accepts(cache_dir, today, tmp_path, fake_client):
    data = analytics.json_safe(analytics.payload(today, cache_dir))
    ctx = build_context(data, cache_dir)
    v = ctx["series"]["selic_target"]["history"][-1][1]
    bad = {"answer": "The Selic will reach 99.5 next year.", "series_used": ["selic_target"], "cannot_answer": False}
    good = {"answer": f"The Selic target is {v}.", "series_used": ["selic_target"], "cannot_answer": False}
    client = fake_client([bad, good])
    res = ask_one("Where is the Selic?", ctx, LLM("live", client=client, recordings=tmp_path))
    assert client.calls == 2 and res["answer"] == good["answer"]
    assert res["series_used"][0]["source"] == "BCB SGS 432"


def test_ask_needs_citations(cache_dir, today, tmp_path, fake_client):
    ctx = build_context(analytics.json_safe(analytics.payload(today, cache_dir)), cache_dir)
    nocite = {"answer": "Rates are high.", "series_used": [], "cannot_answer": False}
    client = fake_client([nocite, nocite])
    try:
        ask_one("Are rates high?", ctx, LLM("live", client=client, recordings=tmp_path))
        raise AssertionError("should have failed")
    except ValueError as e:
        assert "series_used is empty" in str(e)


def test_presets_keep_previous_answer_when_api_fails(cache_dir, today, tmp_path, fake_client):
    out = tmp_path / "ask.json"
    prev = {
        "items": [
            {"question": q, "answer": "old", "series_used": [], "cannot_answer": False}
            for q in __import__("macro_terminal.ask", fromlist=["PRESETS"]).PRESETS
        ]
    }
    out.write_text(json.dumps(prev), encoding="utf-8")
    res = run_presets("demo", today, out, recordings=tmp_path / "rec", cache_root=cache_dir)
    assert all(i["answer"] == "old" and i["stale_reason"] for i in res["items"])


def test_portuguese_decimal_comma():
    assert numbers_in("o PTAX passou de 5,22 para 5,06; 1,234.5 pontos") == ["5.22", "5.06", "1234.5"]


# ---------------------------------------------------------------- newsletter
def test_line_svg():
    s = pd.Series([1.0, 2.0, 1.5], index=pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01"]))
    svg = line_svg("Title", "unit", [("A", s)])
    assert svg.startswith("<svg") and "polyline" in svg and "A 1.50" in svg


def test_newsletter_md_html_and_archive(cache_dir, today, tmp_path):
    brief = {
        "date": "2026-10-19",
        "brief": {"headline": "Quiet week", "points": ["a", "b", "c"], "risks": ["r"], "data_caveats": []},
        "meta": {"model": "m"},
    }
    bp = tmp_path / "brief.json"
    bp.write_text(json.dumps(brief), encoding="utf-8")
    news = tmp_path / "news"
    html_path = write_newsletter(bp, news, today, cache_dir)
    assert html_path.name == "2026-W43.html" and html_path.read_text(encoding="utf-8").count("<svg") == 3
    md = (news / "2026-W43.md").read_text(encoding="utf-8")
    assert "![rates](2026-W43/rates.svg)" in md and (news / "2026-W43" / "indices.svg").exists()
    assert editions(news)[0]["headline"] == "Quiet week"
    site = tmp_path / "site"
    build.build(site, today, cache_dir, brief_path=bp, ask_path=tmp_path / "none.json", news_dir=news)
    assert (site / "newsletter" / "2026-W43.html").exists()
