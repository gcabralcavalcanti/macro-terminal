# Macro Terminal

A one-page dashboard, styled like a trading terminal, that shows where the Brazilian and US economies and markets
stand today, flags what changed, and has an AI write a short daily summary that is checked against the data.

![Public data only](https://img.shields.io/badge/data-public%20only-2ea44f)
![Built with AI assistance](https://img.shields.io/badge/built%20with-AI%20assistance-6f42c1)

**Live:** https://gcabralcavalcanti.github.io/macro-terminal/

![Macro tab](docs/screenshots/macro.png)

## Results

- Interest rates, inflation, the dollar and unemployment for Brazil and the US, plus what economists expect for this
  year and next, on one screen.
- Prices and risk for 15 large Brazilian and US stocks, and quarterly results for 7 Brazilian companies taken from
  their official filings.
- Every download is checked before it is used. On the first run the checks caught a month missing from the US
  inflation data and a Brazilian stock whose trading code had changed ([data status](docs/screenshots/status.png)).
- The AI summary costs less than a tenth of a US cent and every number in it is confirmed against the data
  ([example](docs/screenshots/brief.png)).

## Run it

```bash
pip install -r requirements.txt
python demo.py
```

Builds the page and opens it in your browser. Runs without an API key (the password that lets a program use
Claude), replaying recorded answers. Set `ANTHROPIC_API_KEY` to call Claude live. `python demo.py --refresh` downloads today's data first.

Tabs: overview, price chart, company results, risk, AI summary, questions, weekly newsletter, data status.
Keys `1`–`8` switch tabs.

## How it works

1. Downloads public data: Brazil's central bank, the US Federal Reserve's public database (FRED), stock prices, and company filings.
2. Checks each download for gaps, wrong dates and wrong units. If a source fails, the page keeps the last good
   copy and says so.
3. Computes the tables, charts and risk numbers, and raises alerts from fixed rules (for example, inflation above
   the official target band).
4. Sends the day's numbers to Claude, which writes the summary and answers a few preset questions. The code rejects
   any answer that contains a number not found in the data.
5. Writes the web page (a single page that needs no server) and a weekly newsletter. GitHub repeats all of this
   automatically every weekday and publishes the page.

Other ways to run it:

- **From another program:** a webhook (a web address that starts the update when another program calls it) lets
  any tool trigger a refresh.
- **Weekly message:** a ready-made workflow for n8n, a visual automation tool, starts the update every Monday and
  sends the summary to a Telegram chat (`docs/n8n/`).
- **Readable by other tools:** the page also publishes a small file, `latest.json`, with the date, the summary and
  the alerts.
- **In a container:** a `Dockerfile` packages the program with everything it needs, so it runs the same way on any
  machine; GitHub rebuilds it and runs the tests on every change.

How to operate all of this, and what to do when a source or the publishing step fails, is in [RUNBOOK.md](RUNBOOK.md).

## Data

Public sources only: Banco Central do Brasil (rates, inflation, exchange rate, market expectations), FRED (US data),
Yahoo Finance (daily prices) and CVM, Brazil's securities regulator (company results and announcements). The last
good copy of each dataset is kept in `data/`, so the page works offline.

## Publish it (GitHub Pages)

1. In the repository, open **Settings → Pages**.
2. Under **Build and deployment → Source**, choose **GitHub Actions**.
3. Open **Actions → update → Run workflow**. When it finishes, the page is at the link above.

Optional: to have the AI summary written live, add the secret `ANTHROPIC_API_KEY` in
**Settings → Secrets and variables → Actions**. Without it, the page shows the last recorded summary.

## Limits

- Daily closing prices, not real time. Yahoo Finance is unofficial and may stop answering.
- Company results cover Brazilian non-financial companies only.
- The check catches made-up numbers, not a wrong interpretation of real ones.
- Asking new questions works only on your own computer (`python -m macro_terminal serve`); the public page shows
  preset answers. Not investment advice.

## How AI was used

I use Claude (Claude Code and the API) for coding, review and documentation. The questions, modelling choices,
validation and conclusions are mine.

MIT License.
