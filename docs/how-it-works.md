# How it works

## How I use it

I built this in October 2026, so what follows is how it is set up and how I plan to use it, not a long habit yet.

- **On its own:** once the page is published, GitHub refreshes the data every weekday at 19:30 Brasília time, after
  the markets close. The AI summary and the preset answers are rewritten only on Mondays, to keep the cost near zero;
  on the other days the page shows Monday's text with its date. The program writes only to the page, so nothing waits
  for my approval.
- **If I turn it on:** the n8n workflow starts the Monday run and sends me the summary and the alerts on Telegram.
- **What I plan to do:** open the page before studying or discussing the macro picture, look at the alerts first, and,
  on my computer, ask the ASK tab about a specific number.

## The steps

1. **Download** public data: Brazil's central bank (rates, inflation, exchange rate, unemployment and the weekly
   survey of economists' expectations), the US Federal Reserve's public database FRED, daily stock prices from
   Yahoo Finance, and company results and announcements from CVM, Brazil's securities regulator.
2. **Check** each download before using it: gaps, unreadable or future dates, data that stopped updating, and values
   outside a plausible range (which usually means the source changed its units). A download that fails a check is
   not used; the page keeps the last good copy and marks the dataset as stale.
   On the first run the checks caught a month missing from the US inflation data and a Brazilian stock whose trading
   code had changed ([data status screen](screenshots/status.png)).
3. **Compute** the tables, charts and risk numbers (volatility, beta to the local index, worst drop, Sharpe ratio,
   correlations), quarterly company results, and alerts from fixed rules: a change in the Selic or the Fed's rate,
   inflation outside Brazil's 1.5% to 4.5% target band, a move of 2% or more in the dollar or an index, 5% or more in a
   stock. The alerts use no AI.
4. **Write** with Claude: the code picks every number and sends them to the model, which writes the summary and
   answers a few preset questions. This happens on Mondays; the other days the page shows Monday's text with its date. The answer must follow a fixed format, cite only series that exist, and contain no
   number missing from the data; otherwise it is asked once more and then dropped.
5. **Publish** a single page that needs no server (the data is embedded in it), a weekly newsletter in Markdown and
   HTML with three charts, and `latest.json`, a small file with the date, the summary and the alerts.

## The page

Tabs: overview (macro tables and expectations), price chart with moving averages and volume, company results, risk,
AI summary, questions, weekly newsletter, and data status (each source, when it was last updated, and any check that
fired). Keys `1` to `8` switch tabs; typing `VALE3 FA` in the command line opens that company's results; a link like
`index.html#risk/AAPL` opens a tab directly. It works on phones.

## Recorded answers and cost

Every answer from Claude is saved in `data/recorded/`. The same input is never paid for twice, and without an API key
the page replays the saved answers. The model is `claude-haiku-5-5` with a cap on calls per run: a summary costs about
US$ 0.0005 and the five preset questions about US$ 0.003. Live questions need `python -m macro_terminal serve`, which
runs only on your computer so the key never leaves it.

## Command line

| Command | What it does |
|---|---|
| `python demo.py` | builds the page from the saved data and opens it |
| `python demo.py --refresh` | downloads today's data first (`--live` also calls Claude) |
| `python -m macro_terminal collect` | downloads and checks the data (`--only prices,filings` for some sources) |
| `python -m macro_terminal brief` / `ask` | writes the summary / answers the preset questions |
| `python -m macro_terminal ask "your question"` | one live question |
| `python -m macro_terminal newsletter` / `build` | writes the newsletter / the page |
| `python -m macro_terminal serve` | local page with a box for live questions |
| `python -m pytest -q` | tests, no internet needed |

## Folders

`macro_terminal/` the code (sources, checks, page template, answer formats) · `tests/` · `data/` the last good copy of
each dataset and the recorded answers · `output/` what the code writes (only the sample newsletter is kept in git) ·
`docs/` screenshots, this page and the n8n workflow.

## Use it with other tickers or series

Edit `macro_terminal/config.py`: `TICKERS` for stocks (Yahoo symbol, region, name, CVM code for Brazilian results),
`SGS` and `FRED` for macro series (code, label, unit, frequency, plausible range). Then run `python demo.py --refresh`.
