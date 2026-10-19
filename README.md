# Macro Terminal

A terminal-style dashboard of Brazilian and US macro and market data, with rule-based alerts, an AI daily brief
and questions answered from the data, built from public sources and published as a static page.

![Public data only](https://img.shields.io/badge/data-public%20only-2ea44f)
![Built with AI assistance](https://img.shields.io/badge/built%20with-AI%20assistance-6f42c1)

**Live:** https://gcabralcavalcanti.github.io/macro-terminal/

![Macro tab](docs/screenshots/macro.png)

## Results

| | Number | Source in this repo |
|---|---|---|
| Data | 6 public sources, 18 securities, 8 quarters of CVM income statements for 7 companies, 59 recent filings | `data/cache/_status.json` |
| Checks | Every download checked for missing values, dates and units; on 2026-10-19 they flagged a missing US CPI month at the source | `data/cache/_status.json` |
| AI brief | 1 API call, 2,431 input + 556 output tokens, about US$ 0.0005; every number in the text found in the input | `data/brief.json` |
| Ask | 5 preset questions answered with 1 to 3 cited series each, about US$ 0.003 for the five | `data/ask.json` |
| Tests | 29 tests, no network, with a fake API client | `tests/` |

More screens: [price](docs/screenshots/price.png) · [fundamentals](docs/screenshots/fundamentals.png) ·
[risk](docs/screenshots/risk.png) · [brief](docs/screenshots/brief.png) · [ask](docs/screenshots/ask.png) ·
[newsletter](docs/screenshots/news.png) · [data status](docs/screenshots/status.png) · [phone](docs/screenshots/mobile.png)

## Run it

```bash
pip install -r requirements.txt
python demo.py
```

Builds the page from the committed data and recorded AI answers and opens it; no API key or network needed.
`python demo.py --refresh` downloads fresh data first; add `--live` to call the API (needs `ANTHROPIC_API_KEY`).
`python -m macro_terminal serve` adds a live question box to the ASK tab (127.0.0.1 only). `python -m pytest -q` runs the tests.

Tabs: 1 MACRO · 2 GP (price, moving averages, volume) · 3 FA (fundamentals) · 4 RISK (volatility, beta, drawdown,
Sharpe, correlation) · 5 BRIEF · 6 ASK · 7 NEWS (weekly editions) · 8 STATUS. Keys `1`–`8` switch tabs; type
`VALE3 FA` in the command line; links like `index.html#risk/AAPL` open a tab directly.

## How it works

1. **Collect** (`macro_terminal/sources/`): BCB, Focus, FRED, Yahoo Finance and CVM.
2. **Check** (`checks.py`): missing values, unreadable or future dates, staleness, a plausible range per series to
   catch unit changes, price and revenue scale. A failed source or check keeps the last good copy, marked STALE.
3. **Compute** (`analytics.py`, `alerts.py`): macro tables, Focus changes, risk metrics, quarterly fundamentals
   (Q4 = annual minus nine months), and alerts from fixed rules (policy rate change, IPCA outside the 1.5–4.5% band,
   moves of 2%+ in FX or indices).
4. **Write** (`brief.py`, `ask.py`): Claude writes the brief and answers questions in JSON checked against a schema.
   The code supplies every number; an answer with a number not in the input, or a citation outside the closed list
   of series, is retried once and then dropped.
5. **Publish** (`build.py`, `newsletter.py`): a static page in `site/` (data embedded, opens from disk) and a weekly
   edition in Markdown and HTML with three SVG charts (`reports/newsletter/`). GitHub Actions
   (`.github/workflows/update.yml`) runs this on weekdays and deploys to Pages; the AI calls run on Mondays.

## Data

| Source | Series |
|---|---|
| BCB SGS | Selic target, IPCA (12m and m/m), USD/BRL PTAX, unemployment |
| BCB Focus | median expectations for IPCA, Selic, USD/BRL and GDP, this year and next |
| FRED (public CSV, no key) | fed funds, 2y and 10y Treasuries, CPI, unemployment |
| Yahoo Finance | 2 years of daily prices: 8 B3 stocks, 7 US stocks, Ibovespa, S&P 500, USD/BRL |
| CVM open data | quarterly income statements (ITR/DFP) and filings (IPE) |

All public. `data/cache/` holds the last good copy of each dataset, so the page works offline.

## Limits

- Yahoo Finance is unofficial and can change or throttle; it is the first source to show STALE.
- Fundamentals cover Brazilian non-financial companies; banks file a different income statement.
- Daily closes, not real time. Beta and correlation use each market's own trading calendar.
- The number check catches invented numbers, not a wrong reading of real ones.
- Live questions need the local server; the public page shows preset answers. Not investment advice.

## How AI was used

I use Claude (Claude Code and the API) for coding, review and documentation. The questions, modelling choices,
validation and conclusions are mine. In the product, `claude-haiku-5-5` writes the brief and answers questions,
capped at 2 calls per brief and 12 per set of questions, with every answer recorded so the same input is never paid
twice.

The BCB, FRED and CVM download code is adapted from my thesis data pipeline (DCF valuation of Gerdau).

MIT License.
