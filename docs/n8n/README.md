# n8n flow: weekly refresh and Telegram alert

`macro-terminal-refresh.json` is an n8n workflow. Every Monday at 20:00 (or when its webhook is called) it:

1. asks GitHub to start the `update` job of this repository (the same POST shown in `RUNBOOK.md`);
2. waits 15 minutes for the job to finish;
3. reads `latest.json` from the published page: date, AI summary headline, alerts, failed sources;
4. writes a short message, with a warning if the page was not rebuilt;
5. sends it to a Telegram chat.

## Set it up

1. In n8n: **Workflows → Import from file** and choose `macro-terminal-refresh.json`.
2. Create two credentials in n8n (they stay in n8n, never in this repository):
   - **Header Auth** named `GitHub token (macro-terminal)`: name `Authorization`, value `Bearer <token>`, where the
     token is a fine-grained GitHub token for this repository with "Contents: read and write".
   - **Telegram** named `Telegram bot`, with the token from @BotFather.
3. In the node "Send to Telegram", replace `YOUR_TELEGRAM_CHAT_ID` with your chat id, then turn the workflow on.

The webhook node gives a URL that starts the same flow from any other tool.
