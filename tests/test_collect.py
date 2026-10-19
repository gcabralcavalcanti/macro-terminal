"""Collection with recorded payloads: parsing, checks and the cache fallback (no network)."""

import io
import json
import zipfile

import pandas as pd

from macro_terminal import cache, checks, collect
from macro_terminal.sources import bcb, cvm, fred, market

from .conftest import FIXTURES


def test_sgs_parse_and_future_dates_dropped(today):
    df = bcb.parse_sgs(json.loads((FIXTURES / "sgs_432.json").read_text()), "selic_target")
    spec = {"selic_target": ("Selic target", "% p.a.", "daily", (0.0, 60.0))}
    clean, issues = checks.check_series(df, spec, today, "SGS")
    assert len(clean) == 3 and clean["date"].max() == pd.Timestamp("2026-10-16")
    assert any("after today" in i["msg"] for i in issues)
    assert not checks.has_errors(issues)


def test_unit_change_is_rejected(today):
    # the source starts sending the rate as a fraction (0.1375) instead of percent (13.75)... and in basis points
    df = pd.DataFrame({"date": ["2026-10-15", "2026-10-16"], "series": "selic_target", "value": [13.75, 1375.0]})
    spec = {"selic_target": ("Selic target", "% p.a.", "daily", (0.0, 60.0))}
    _, issues = checks.check_series(df, spec, today, "SGS")
    assert checks.has_errors(issues)


def test_missing_values_and_stale_series(today):
    df = pd.DataFrame(
        {"date": pd.date_range("2026-01-01", periods=10, freq="MS")[:5], "series": "x", "value": [1, None, None, 2, 3]}
    )
    spec = {"x": ("X", "%", "monthly", (0, 10))}
    _, issues = checks.check_series(df, spec, today, "T")
    assert checks.has_errors(issues)  # 40% missing
    assert any("days old" in i["msg"] for i in issues)  # last obs in May


def test_fred_csv_with_holiday_dot():
    df = fred.parse_csv((FIXTURES / "fred_dff.csv").read_text(), "fed_funds")
    assert len(df) == 4 and df["value"].isna().sum() == 1


def test_focus_keeps_end_of_year_all_respondents():
    df = bcb.parse_focus(json.loads((FIXTURES / "focus_cambio.json").read_text(encoding="utf-8")), "Câmbio", "focus_fx")
    assert df["value"].tolist() == [5.13]


def test_market_tidy_and_fill_from_cache():
    idx = pd.to_datetime(["2026-10-16", "2026-10-19"])
    cols = pd.MultiIndex.from_product([["Close", "Volume"], ["AAPL", "PETR4.SA"]])
    raw = pd.DataFrame([[10, 20, 1, 2], [11, None, 1, None]], index=idx, columns=cols)
    raw[("Open", "AAPL")] = raw[("High", "AAPL")] = raw[("Low", "AAPL")] = 1.0
    raw[("Open", "PETR4.SA")] = raw[("High", "PETR4.SA")] = raw[("Low", "PETR4.SA")] = 1.0
    out = market.tidy(raw, {"AAPL": "AAPL", "PETR4.SA": "PETR4"})
    assert set(out["ticker"]) == {"AAPL", "PETR4"} and len(out) == 3
    old = pd.DataFrame(
        {"date": ["2026-10-16"], "ticker": ["VALE3"], "open": 1, "high": 1, "low": 1, "close": 60, "volume": 5}
    )
    filled, missing = market.fill_from_cache(out, old)
    assert missing == ["VALE3"] and "VALE3" in set(filled["ticker"])


def test_price_checks(today):
    df = pd.DataFrame(
        {
            "date": pd.bdate_range(end="2026-10-19", periods=3),
            "ticker": "X",
            "open": 1,
            "high": 1,
            "low": 1,
            "close": [10, 10, 20],
            "volume": [1, 1, 1],
        }
    )
    _, issues = checks.check_prices(df, ["X", "Y"], today)
    msgs = " ".join(i["msg"] for i in issues)
    assert "no data for Y" in msgs and "daily move" in msgs and not checks.has_errors(issues)


def _dre_rows(kind, ini, fim, value, conta="3.01", escala="MIL"):
    return {
        "CNPJ_CIA": "x",
        "DT_REFER": fim,
        "VERSAO": "1",
        "DENOM_CIA": "X",
        "CD_CVM": "9512",
        "GRUPO_DFP": "",
        "MOEDA": "REAL",
        "ESCALA_MOEDA": escala,
        "ORDEM_EXERC": "ÚLTIMO",
        "DT_INI_EXERC": ini,
        "DT_FIM_EXERC": fim,
        "CD_CONTA": conta,
        "DS_CONTA": "Receita",
        "VL_CONTA": str(value),
        "ST_CONTA_FIXA": "S",
    }


def _zip(tmp_path, kind, year, rows):
    path = tmp_path / f"{kind}_{year}.zip"
    buf = io.StringIO()
    pd.DataFrame(rows).to_csv(buf, sep=";", index=False)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"{kind}_cia_aberta_DRE_con_{year}.csv", buf.getvalue().encode("latin-1"))
    return path


def test_cvm_quarters_and_q4_derivation(tmp_path):
    itr = _zip(
        tmp_path,
        "itr",
        2025,
        [
            _dre_rows("itr", "2025-01-01", "2025-03-31", 100),
            _dre_rows("itr", "2025-04-01", "2025-06-30", 110),
            _dre_rows("itr", "2025-01-01", "2025-06-30", 210),  # year to date: ignored as a quarter
            _dre_rows("itr", "2025-07-01", "2025-09-30", 120),
            _dre_rows("itr", "2025-01-01", "2025-09-30", 330),  # nine months, used for Q4
        ],
    )
    dfp = _zip(tmp_path, "dfp", 2025, [_dre_rows("dfp", "2025-01-01", "2025-12-31", 460)])
    rows = pd.concat([cvm.read_statement(itr, "itr", 2025, {9512}), cvm.read_statement(dfp, "dfp", 2025, {9512})])
    q = cvm.quarterly(rows, {9512: "PETR4"})
    rev = q[q["metric"] == "revenue"].set_index("period")["value"]
    assert rev.to_dict() == {"2025Q1": 100, "2025Q2": 110, "2025Q3": 120, "2025Q4": 130}


def test_fundamentals_scale_check():
    df = pd.DataFrame(
        {"ticker": "PETR4", "period": "2026Q2", "metric": "revenue", "value": [169_530_000_000.0]}
    )  # units left unconverted
    _, issues = checks.check_fundamentals(df)
    assert checks.has_errors(issues)


def test_filings_parse():
    csv = (
        "CNPJ_Companhia;Nome_Companhia;Codigo_CVM;Data_Referencia;Categoria;Tipo;Especie;Assunto;Data_Entrega;"
        "Tipo_Apresentacao;Protocolo_Entrega;Versao;Link_Download\n"
        "x;PETROBRAS;9512;2026-10-16;Fato Relevante;;;Dividendos;2026-10-16;AP;1;1;https://rad/x\n"
        "x;PETROBRAS;9512;2026-10-16;Valores Mobiliários negociados e detidos (art. 11 da Instr. CVM nº 358);;;"
        ";2026-10-16;AP;2;1;https://rad/y\n"
    ).encode("latin-1")
    df = cvm.parse_filings(csv, {9512: "PETR4"})
    assert df["category"].tolist() == ["FR"] and df["subject"].iloc[0] == "Dividendos"


def test_failed_source_keeps_cache_and_marks_stale(tmp_path):
    root = tmp_path / "c"
    good = pd.DataFrame({"date": ["2026-10-16"], "series": "x", "value": [1.0]})
    cache.save("macro_br", good, "src", [], root=root)

    def boom():
        raise ConnectionError("api down")

    assert collect.run_one("macro_br", boom, lambda d: (d, []), root=root) == "stale"
    st = cache.read_status(root)["macro_br"]
    assert st["status"] == "stale" and "api down" in st["error"] and st["fetched_at"]
    assert cache.load("macro_br", root).equals(good)


def test_rejected_by_checks_keeps_cache(tmp_path):
    root = tmp_path / "c"
    cache.save(
        "prices",
        pd.DataFrame({"date": ["2026-10-16"], "ticker": ["X"], "close": [1.0], "volume": [1]}),
        "src",
        [],
        root=root,
    )
    bad = pd.DataFrame({"date": ["2026-10-17"], "ticker": ["X"], "close": [-1.0], "volume": [1]})
    status = collect.run_one(
        "prices", lambda: bad, lambda d: checks.check_prices(d, ["X"], pd.Timestamp("2026-10-19").date()), root=root
    )
    assert status == "stale" and cache.load("prices", root)["close"].iloc[0] == 1.0
