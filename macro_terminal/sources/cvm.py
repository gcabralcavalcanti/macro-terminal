"""CVM open data: quarterly income statements (ITR/DFP) and filings (IPE), read from the zips without extracting.
Q4 is not filed as a quarter, so Q4 = annual (DFP) minus nine months year-to-date (ITR Q3). Values in BRL thousands."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

from .. import config, net

ACCOUNTS = {"3.01": "revenue", "3.03": "gross_profit", "3.05": "ebit", "3.11": "net_income"}

# filing categories worth showing, with a short code in the spirit of 8-K / 10-Q
CATEGORIES = {
    "Fato Relevante": ("FR", "Material fact"),
    "Comunicado ao Mercado": ("CM", "Market notice"),
    "Aviso aos Acionistas": ("AA", "Shareholder notice"),
    "Dados Econômico-Financeiros": ("DEF", "Financial data / results"),
    "Assembleia": ("AGM", "Shareholder meeting"),
    "Reunião da Administração": ("BRD", "Board / management meeting"),
    "Calendário de Eventos Corporativos": ("CAL", "Corporate calendar"),
    "Relatório Proventos": ("DIV", "Dividends report"),
}


def _zip_url(kind: str, year: int) -> str:
    return f"{config.CVM_BASE}/{kind.upper()}/DADOS/{kind}_cia_aberta_{year}.zip"


def read_statement(zip_path: Path, kind: str, year: int, codes: set[int]) -> pd.DataFrame:
    """Consolidated income statement rows of the selected companies from one ITR/DFP zip."""
    member = f"{kind}_cia_aberta_DRE_con_{year}.csv"
    with zipfile.ZipFile(zip_path) as z, z.open(member) as f:
        df = pd.read_csv(io.TextIOWrapper(f, encoding="latin-1"), sep=";", dtype=str)
    df["CD_CVM"] = pd.to_numeric(df["CD_CVM"], errors="coerce")
    df = df[df["CD_CVM"].isin(codes) & df["CD_CONTA"].isin(ACCOUNTS)]
    return df.assign(KIND=kind)


def quarterly(rows: pd.DataFrame, code_to_ticker: dict[int, str]) -> pd.DataFrame:
    """ITR + DFP income statement rows -> one value per (ticker, quarter, metric), BRL thousands."""
    if rows.empty:
        return pd.DataFrame(columns=["ticker", "period", "period_end", "metric", "value"])
    d = rows.copy()
    d = d[d["ORDEM_EXERC"].str.upper().str.startswith("ÚLTIMO") | (d["ORDEM_EXERC"].str.upper() == "ULTIMO")]
    d["value"] = pd.to_numeric(d["VL_CONTA"], errors="coerce")
    d.loc[d["ESCALA_MOEDA"].str.upper() == "UNIDADE", "value"] /= 1000.0
    d["ini"] = pd.to_datetime(d["DT_INI_EXERC"])
    d["fim"] = pd.to_datetime(d["DT_FIM_EXERC"])
    d["VERSAO"] = pd.to_numeric(d["VERSAO"], errors="coerce")
    d = d.sort_values("VERSAO").drop_duplicates(["KIND", "CD_CVM", "CD_CONTA", "ini", "fim"], keep="last")
    d["metric"] = d["CD_CONTA"].map(ACCOUNTS)
    d["ticker"] = d["CD_CVM"].map(code_to_ticker)
    span = (d["fim"] - d["ini"]).dt.days

    q = d[(d["KIND"] == "itr") & (span < 100)][["ticker", "fim", "metric", "value"]]
    ytd9 = d[(d["KIND"] == "itr") & (d["ini"].dt.month == 1) & (d["fim"].dt.month == 9)]
    annual = d[(d["KIND"] == "dfp") & (d["ini"].dt.month == 1) & (d["fim"].dt.month == 12)]
    q4 = annual.assign(year=annual["fim"].dt.year).merge(
        ytd9.assign(year=ytd9["fim"].dt.year)[["ticker", "metric", "year", "value"]],
        on=["ticker", "metric", "year"],
        suffixes=("", "_9m"),
    )
    q4 = q4.assign(value=q4["value"] - q4["value_9m"])[["ticker", "fim", "metric", "value"]]

    out = pd.concat([q, q4], ignore_index=True).rename(columns={"fim": "period_end"})
    out["period"] = out["period_end"].dt.year.astype(str) + "Q" + out["period_end"].dt.quarter.astype(str)
    out = out.drop_duplicates(["ticker", "period", "metric"], keep="first")
    last = sorted(out["period"].unique())[-config.FUNDAMENTAL_QUARTERS :]
    out = out[out["period"].isin(last)]
    return out.sort_values(["ticker", "period", "metric"])[["ticker", "period", "period_end", "metric", "value"]]


def fetch_fundamentals(today: date) -> pd.DataFrame:
    codes = {v[3]: k for k, v in config.TICKERS.items() if v[3] and k not in config.NO_FUNDAMENTALS}
    parts = []
    for kind, years in (("itr", range(today.year - 2, today.year + 1)), ("dfp", range(today.year - 2, today.year))):
        for y in years:
            path = config.DOWNLOADS / f"{kind}_{y}.zip"
            try:
                net.download(_zip_url(kind, y), path, max_age_days=config.FUNDAMENTALS_MAX_AGE_DAYS)
            except net.FetchError:
                if y == today.year:  # the current year may not be published yet
                    continue
                raise
            parts.append(read_statement(path, kind, y, set(codes)))
    return quarterly(pd.concat(parts, ignore_index=True), codes)


def parse_filings(csv_bytes: bytes, code_to_ticker: dict[int, str]) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(csv_bytes), sep=";", encoding="latin-1", dtype=str)
    df["code"] = pd.to_numeric(df["Codigo_CVM"], errors="coerce")
    df = df[df["code"].isin(code_to_ticker) & df["Categoria"].isin(CATEGORIES)]
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df["Data_Entrega"], errors="coerce"),
            "ticker": df["code"].map(code_to_ticker),
            "category": df["Categoria"].map(lambda c: CATEGORIES[c][0]),
            "category_en": df["Categoria"].map(lambda c: CATEGORIES[c][1]),
            "subject": df["Assunto"].fillna(df["Tipo"]).fillna("").str.strip().str.slice(0, 140),
            "link": df["Link_Download"].fillna(""),
        }
    )
    return out.sort_values("date", ascending=False).drop_duplicates(["ticker", "category", "subject", "date"])


def fetch_filings(today: date) -> pd.DataFrame:
    codes = {v[3]: k for k, v in config.TICKERS.items() if v[3]}
    parts = []
    for y in (today.year, today.year - 1):
        path = config.DOWNLOADS / f"ipe_{y}.zip"
        net.download(_zip_url("ipe", y), path, max_age_days=0.5)
        with zipfile.ZipFile(path) as z:
            parts.append(parse_filings(z.read(f"ipe_cia_aberta_{y}.csv"), codes))
        if sum(len(p) for p in parts) >= config.FILINGS_KEEP * 3:
            break
    df = pd.concat(parts, ignore_index=True).sort_values("date", ascending=False)
    # keep the most recent filings overall and at least a few per company
    top = df.head(config.FILINGS_KEEP)
    per = df.groupby("ticker").head(6)
    return pd.concat([top, per]).drop_duplicates().sort_values("date", ascending=False).reset_index(drop=True)
