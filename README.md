# Macro Terminal

A terminal-style dashboard of Brazilian and US macro and market data, built only from public sources.
Python collects and checks the data, writes a static page (no server), and the Claude API writes a short
daily brief from the day's numbers. GitHub Actions refreshes and publishes it.

**Live:** https://gcabralcavalcanti.github.io/macro-terminal/

![Macro tab](docs/screenshots/macro.png)

| Price, moving averages and volume | Quarterly fundamentals (CVM filings) |
|---|---|
| ![Price](docs/screenshots/price.png) | ![Fundamentals](docs/screenshots/fundamentals.png) |
| **Risk: volatility, beta, drawdown, Sharpe, correlation** | **AI brief (checked against the input numbers)** |
| ![Risk](docs/screenshots/risk.png) | ![Brief](docs/screenshots/brief.png) |

Also: a data status tab (every check, every source, live or stale) and a phone layout ([screenshot](docs/screenshots/mobile.png)).

## What it shows

| Tab | Content | Source |
|---|---|---|
| 1 MACRO | Selic target, IPCA (12m and m/m), USD/BRL PTAX, unemployment, real rate; fed funds, 2y/10y Treasuries, curve, CPI y/y, unemployment; Focus survey medians and 4-week change | BCB SGS, BCB Focus (Olinda), FRED |
| 2 GP | Daily close with 20/50/200-day moving averages, volume, 52-week range | Yahoo Finance (yfinance) |
| 3 FA | Revenue, gross profit, EBIT, net income and margins, last 8 quarters | CVM open data (ITR/DFP) |
| 4 RISK | Annualised volatility, beta to the local index, max drawdown, Sharpe (risk-free = Selic or fed funds), correlation heatmap | computed from prices |
| 5 BRIEF | Headline, 3–5 points, risks, data caveats | Claude API |
| 6 STATUS | Each dataset: live / stale / missing, last observation, checks that fired | the pipeline itself |
| right panel | Recent filings: material facts, market notices, results, meetings | CVM open data (IPE) |

Universe: 8 Brazilian stocks, 7 US stocks, Ibovespa, S&P 500 and USD/BRL (edit `macro_terminal/config.py`).
Keyboard: `1`–`6` switch tabs, arrows move through the list, type `VALE3 FA` and Enter in the command line.
Links like `index.html#risk/AAPL` open a tab and security directly.

## How it works

```
collect  ->  checks  ->  cache (data/cache)  ->  analytics  ->  brief (Claude)  ->  build (site/)  ->  GitHub Pages
```

- **Checks on every download** (`checks.py`): missing values per series (over 20% rejects), unreadable, duplicated or
  future dates (the Selic target series is published up to the next meeting), staleness by frequency, plausible range
  per series to catch unit changes (Selic 0–60% p.a., USD/BRL 1–15...), non-positive prices, daily moves above 40%,
  revenue scale (catches thousands vs units).
- **A failing source never breaks the page.** Network error or failed check: the last good copy stays, the dataset is
  marked STALE on screen with the error. A ticker missing from today's download keeps its cached history.
- **Static page:** the data goes into `site/data.js` (`window.TERMINAL = {...}`), so `site/index.html` opens straight
  from disk. Plain HTML/CSS/JS and canvas charts, no libraries, no external requests.
- **Fundamentals:** the CVM zips are read without extracting; Q4 is not filed as a quarter, so Q4 = annual (DFP) minus
  nine months year-to-date (ITR Q3). The zips (~100 MB) are refreshed weekly.

## The AI brief

The code picks and computes every number; the model only writes about them (`brief.py`).

| Concern | What the code does |
|---|---|
| Format | JSON Schema through structured outputs; validated again locally with stricter rules (3–5 points, lengths) |
| Hallucinated numbers | every number in the text must exist in the input data (rounding allowed); otherwise one retry with the error, then stop |
| Cost | `claude-haiku-5-5`, `max_tokens` 700, at most 2 calls per run; a brief is ~2,400 input and ~550 output tokens, about US$ 0.0005 |
| Repeats | every accepted answer is recorded in `recordings/`; the same input is never paid twice |
| No key / API down | the latest recorded brief is shown, labelled with its date |
| Reliability | 45 s timeout, SDK retries for network/429/5xx, one JSON log line per call (`logs/`, tokens and cost) |
| Secrets | `ANTHROPIC_API_KEY` from the environment or `.env` (never committed) |

`python -m macro_terminal newsletter` turns the latest brief plus the week's numbers into Markdown
(`newsletter/2026-W43.md`), with no extra API call.

## Run it

```bash
pip install -r requirements.txt
python -m macro_terminal all            # collect + brief + newsletter + build
python -m macro_terminal all --demo     # same, never calls the API
python -m pytest -q                     # 19 tests, no network
```

Then open `site/index.html`. Steps can run alone: `collect [--only prices,filings]`, `brief`, `newsletter`, `build`.

## Scheduled run (GitHub Actions)

`.github/workflows/update.yml` runs on weekdays at 22:30 UTC: tests, collect, brief, build, deploy to Pages.

- Pages: *Settings > Pages > Source: GitHub Actions*.
- Key: *Settings > Secrets and variables > Actions > New repository secret*, name `ANTHROPIC_API_KEY`.
  Without it the workflow still runs and shows the latest recorded brief.
- The AI call runs on Mondays (or on a manual run). Set the repository variable `AI_DAILY=true` for every weekday.
  Measured cost of one brief: 1 call, 2,431 input + 556 output tokens, about US$ 0.0005.
- `actions/cache` keeps the last good data and the CVM zips between runs; the committed `data/cache` is the fallback.

## Layout

```
macro_terminal/   collect.py, checks.py, cache.py, analytics.py, brief.py, llm.py, build.py, newsletter.py
  sources/        bcb.py (SGS, Focus), fred.py, market.py (yfinance), cvm.py (ITR/DFP, IPE)
web/              page template: index.html, terminal.css, terminal.js
site/             generated page (what Pages serves)
data/cache/       last good copy of each dataset + _status.json
schemas/          brief.api.json (sent to the API), brief.strict.json (local validation)
recordings/       recorded AI answers   tests/  fixtures and fake API client
```

## Limits

- Yahoo Finance is unofficial and can change or throttle; it is the first source to show STALE.
- Fundamentals cover Brazilian non-financial companies (banks file a different income statement).
- Beta and correlation use each market's own calendar; FX trades on days the B3 is closed.
- Prices are daily closes, not real time. Not investment advice.

The BCB, FRED and CVM download code is adapted from the author's thesis data pipeline (DCF valuation of Gerdau).

MIT License.
