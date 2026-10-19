"""Page generation and the AI brief, with a synthetic cache and a fake API client (no network, no cost)."""

import json

import jsonschema
import pytest

from macro_terminal import analytics, build, config
from macro_terminal.brief import build_input, number_check, run_brief

GOOD = {
    "headline": "Selic steady at 13.75 while the dollar eases",
    "points": [
        "The Selic target stays at 13.75% p.a.",
        "Focus IPCA for 2026 moved to 5.1.",
        "US 10y yield near 4.5 with a flat curve.",
    ],
    "risks": ["Inflation expectations drifting up."],
    "data_caveats": [],
}


def _strict():
    return json.loads((config.SCHEMAS / "brief.strict.json").read_text(encoding="utf-8"))


def test_payload_numbers(cache_dir, today):
    data = analytics.payload(today, cache_dir)
    assert {w["ticker"] for w in data["watchlist"]} == set(config.TICKERS)
    br = data["risk"]["BR"]
    assert br["rf"] == pytest.approx(13.75, abs=0.05)
    corr = br["corr"]
    i = corr["tickers"].index("IBOV")
    assert corr["matrix"][i][i] == 1.0
    assert all(r["mdd"] <= 0 for r in br["rows"])
    fa = data["fundamentals"]["PETR4"]
    assert fa["rows"]["revenue"] == [120000.0, 120000.0] and fa["rows"]["net_margin"] == [16.7, 16.7]
    assert data["macro"]["focus"][0]["chg_4w"] == pytest.approx(0.1)


def test_build_writes_static_site(cache_dir, today, tmp_path):
    out = tmp_path / "site"
    index = build.build(out, today, cache_dir, brief_path=tmp_path / "none.json")
    assert index.exists() and (out / "terminal.js").exists() and (out / ".nojekyll").exists()
    js = (out / "data.js").read_text(encoding="utf-8")
    assert js.startswith("window.TERMINAL = ")
    data = json.loads(js[len("window.TERMINAL = ") :].rstrip().rstrip(";"))  # valid JSON: no NaN
    assert data["charts"]["PETR4"]["close"] and data["status"]["prices"]["status"] == "live"
    assert '<script src="data.js">' in index.read_text(encoding="utf-8")


def test_strict_schema():
    jsonschema.validate(GOOD, _strict())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**GOOD, "points": GOOD["points"][:2]}, _strict())  # fewer than 3 points
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**GOOD, "extra": 1}, _strict())


def test_number_check():
    source = {"selic": 13.75, "focus": {"year": 2026, "median": 5.1}, "us": {"indicator": "UST 10y", "value": 4.5}}
    assert number_check(GOOD, source) == []
    assert number_check({**GOOD, "headline": "Selic at 13.8"}, source) == []  # rounding allowed
    bad = number_check({**GOOD, "risks": ["A 25 bp hike is likely."]}, source)  # invented number
    assert bad and "25" in bad[0]


def test_brief_live_records_then_replays(cache_dir, today, tmp_path, fake_client):
    rec, out = tmp_path / "rec", tmp_path / "brief.json"
    data = analytics.json_safe(analytics.payload(today, cache_dir))
    source = build_input(data)
    selic = next(r["value"] for r in source["brazil_macro"] if r["indicator"] == "Selic target")
    answer = {
        **GOOD,
        "headline": f"Selic target at {selic}",
        "points": [f"Selic at {selic}."] * 3,
        "risks": ["Inflation."],
    }
    client = fake_client([answer])
    res = run_brief("live", today, out, client=client, recordings=rec, cache_root=cache_dir)
    assert client.calls == 1 and res["meta"]["mode"] == "live" and res["meta"]["number_check"] == "passed"
    sent = client.last_request
    assert sent["model"] == config.MODEL and sent["max_tokens"] == config.MAX_TOKENS
    assert sent["output_config"]["format"]["type"] == "json_schema"
    # same input again: answered from the recording, no new call
    client2 = fake_client([])
    res2 = run_brief("live", today, out, client=client2, recordings=rec, cache_root=cache_dir)
    assert client2.calls == 0 and res2["meta"]["mode"] == "recorded"


def test_brief_retries_once_when_a_number_is_invented(cache_dir, today, tmp_path, fake_client):
    invented = {**GOOD, "headline": "Selic to hit 99.99 next year"}
    fixed = {
        **GOOD,
        "headline": "Markets quiet",
        "points": ["A quiet day for rates.", "A quiet day for the currency.", "Nothing new in the survey."],
        "risks": ["Inflation."],
    }
    client = fake_client([invented, fixed])
    res = run_brief(
        "live", today, tmp_path / "b.json", client=client, recordings=tmp_path / "rec", cache_root=cache_dir
    )
    assert client.calls == 2 and res["brief"]["headline"] == "Markets quiet"
    assert "99.99" in client.last_request["messages"][0]["content"]  # the error was sent back


def test_brief_without_key_uses_latest_recording(cache_dir, today, tmp_path, fake_client):
    rec = tmp_path / "rec"
    fixed = {
        **GOOD,
        "headline": "Markets quiet",
        "points": ["A quiet day for rates.", "A quiet day for the currency.", "Nothing new in the survey."],
        "risks": ["Inflation."],
    }
    run_brief("live", today, tmp_path / "b.json", client=fake_client([fixed]), recordings=rec, cache_root=cache_dir)
    (cache_dir / "prices.csv").write_text((cache_dir / "prices.csv").read_text().replace(",100.0", ",101.0", 1))
    res = run_brief("demo", today, tmp_path / "b.json", recordings=rec, cache_root=cache_dir)
    assert res["brief"]["headline"] == "Markets quiet" and res["meta"]["mode"].startswith("recorded")
