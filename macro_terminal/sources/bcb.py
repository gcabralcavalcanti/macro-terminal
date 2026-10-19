"""Banco Central do Brasil: SGS time series and the Focus market survey (Olinda OData API).

Adapted from the author's thesis collection code (BCB SGS / Focus downloads with retries).
"""
from __future__ import annotations

import urllib.parse
from datetime import date, timedelta

import pandas as pd

from .. import config, net

SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
FOCUS_URL = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais"


def parse_sgs(payload: list[dict], key: str) -> pd.DataFrame:
    """SGS returns [{"data": "dd/mm/yyyy", "valor": "13.75"}, ...]."""
    df = pd.DataFrame(payload)
    if df.empty:
        return pd.DataFrame(columns=["date", "series", "value"])
    return pd.DataFrame({
        "date": pd.to_datetime(df["data"], format="%d/%m/%Y", errors="coerce"),
        "series": key,
        "value": pd.to_numeric(df["valor"], errors="coerce"),
    })


def fetch_sgs(today: date) -> pd.DataFrame:
    parts = []
    for code, (key, *_rest) in config.SGS.items():
        payload = net.get_json(SGS_URL.format(code=code),
                               params={"formato": "json", "dataInicial": config.SGS_START,
                                       "dataFinal": today.strftime("%d/%m/%Y")})
        parts.append(parse_sgs(payload, key))
    return pd.concat(parts, ignore_index=True)


def parse_focus(payload: dict, indicator: str, key: str) -> pd.DataFrame:
    """Keep the all-respondents median (baseCalculo 0) for each survey date and reference year.
    The FX question has two variants (end of year / average); keep end of year."""
    df = pd.DataFrame(payload.get("value", []))
    if df.empty:
        return pd.DataFrame(columns=["date", "series", "ref_year", "value", "respondents"])
    df = df[df["baseCalculo"] == 0]
    if "IndicadorDetalhe" in df:
        detail = df["IndicadorDetalhe"].astype(str)
        df = df[df["IndicadorDetalhe"].isna() | detail.str.contains("Fim", case=False) | (detail == "None")]
    return pd.DataFrame({
        "date": pd.to_datetime(df["Data"], errors="coerce"),
        "series": key,
        "ref_year": pd.to_numeric(df["DataReferencia"], errors="coerce").astype("Int64"),
        "value": pd.to_numeric(df["Mediana"], errors="coerce"),
        "respondents": pd.to_numeric(df.get("numeroRespondentes"), errors="coerce"),
    })


def fetch_focus(today: date) -> pd.DataFrame:
    since = (today - timedelta(weeks=config.FOCUS_WEEKS)).isoformat()
    parts = []
    for indicator, (key, *_rest) in config.FOCUS.items():
        flt = f"Indicador eq '{indicator}' and Data ge '{since}' and baseCalculo eq 0"
        # $select triggers a 403 at the Olinda firewall, so all columns are requested
        url = f"{FOCUS_URL}?$filter={urllib.parse.quote(flt)}&$format=json&$top=5000"
        df = parse_focus(net.get_json(url), indicator, key)
        parts.append(df[df["ref_year"].isin([today.year, today.year + 1])])
    return pd.concat(parts, ignore_index=True)


def focus_spec() -> dict:
    return {key: (label, unit, "weekly", rng) for key, label, unit, rng in config.FOCUS.values()}


def sgs_spec() -> dict:
    return {key: (label, unit, freq, rng) for key, label, unit, freq, rng in config.SGS.values()}
