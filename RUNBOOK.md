# Runbook

How to run, update and publish the terminal, and what to do when something breaks.

## Run it on your computer

```bash
pip install -r requirements.txt
python demo.py               # builds the page from the saved data and opens it
python demo.py --refresh     # downloads today's data first
python -m pytest -q          # tests, no internet needed
```

The page is written to `output/site/index.html`. Without `ANTHROPIC_API_KEY` the AI parts replay saved answers.

With Docker instead of a local Python:

```bash
docker build -t macro-terminal .
docker run --rm -v "$PWD/output:/app/output" macro-terminal    # runs the tests, then builds the page
```

## Update the data

- Automatic: the GitHub job `update` runs every weekday at 19:30 Brasília time. It downloads the data, writes the
  newsletter and publishes the page. The AI summary and the preset questions are refreshed on Mondays.
- By hand: GitHub, then **Actions → update → Run workflow**.
- From another tool (webhook): send a POST to the GitHub API. Use a fine-grained token limited to this repository
  with "Contents: read and write", kept in your password manager or in the tool that calls it, never in the repository.

```bash
curl -X POST https://api.github.com/repos/gcabralcavalcanti/macro-terminal/dispatches \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -d '{"event_type": "refresh", "client_payload": {"brief": true}}'
```

GitHub answers `204` with no body when the run was accepted. `"brief": false` refreshes the data only (no API cost).
The n8n flow in `docs/n8n/` does the same call on a schedule and then sends the summary by Telegram.

After a run, `https://gcabralcavalcanti.github.io/macro-terminal/latest.json` has the date, the summary headline,
the alerts and any source that failed. Other tools can read it.

## Publish (first time)

1. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
2. Optional: **Settings → Secrets and variables → Actions → New repository secret**, name `ANTHROPIC_API_KEY`.
3. **Actions → update → Run workflow.** The page appears at https://gcabralcavalcanti.github.io/macro-terminal/.
   Any later push to `main` also publishes it.

## Automation

| Piece | What it does | Where |
|---|---|---|
| Webhook | a web address that starts the update when another program calls it (the `curl` above) | `.github/workflows/update.yml` |
| n8n workflow | n8n is a visual automation tool; this workflow starts the update every Monday and sends the summary to Telegram | [docs/n8n/](docs/n8n/README.md) |
| `latest.json` | a small file published with the page: date, summary, alerts, failed sources | the live page |
| Docker | packages the program with everything it needs; GitHub builds the image and runs the tests in it on every push | `Dockerfile`, `.github/workflows/ci.yml` |

## When something breaks

| What you see | Why | What to do |
|---|---|---|
| A dataset marked STALE on the page (STATUS tab) | the source was down or its data failed a check | nothing at first; the page keeps the last good copy. If it lasts more than a few days, open the STATUS tab and read the error |
| Prices STALE for days | Yahoo Finance is unofficial and changes without notice | run `pip install -U yfinance` and `python demo.py --refresh`; update the version in `requirements.txt` if it fixes it |
| A stock missing from the list | the ticker changed (Embraer went from EMBR3 to EMBJ3) | fix the symbol in `macro_terminal/config.py` (`TICKERS`) |
| Job fails at "configure-pages" | Pages is not turned on | step 1 of "Publish" above |
| Job fails at "deploy" with a permission error | Pages source is "Deploy from a branch" | change it to "GitHub Actions" |
| AI summary is old | no secret, or it is not Monday | add the secret, or run the job by hand with "brief" ticked; set the repository variable `AI_DAILY=true` for every weekday |
| The AI answer was dropped | it contained a number not in the data, twice | nothing; the page keeps the previous answer. The reason is in `output/logs/` when run locally |

## Cost

The API is called only for the summary and the preset questions: about US$ 0.0035 per Monday run with
`claude-haiku-5-5`. Each run has a cap on calls, and the same input is never paid twice.
