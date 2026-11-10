# LLM Assist Bot for On-Call

A Python proof-of-concept that analyzes request failures from Slack using Splunk logs and a local LLM.

## How it works

1. Receives a Slack message through Flask's `/slack/events` endpoint.
2. Uses a local LLM to extract a request ID.
3. Searches Splunk for matching error logs.
4. Replies in the Slack thread with a short failure summary, a Splunk link, and a logs attachment.

## Run locally

Requires Python, `curl`, access to Splunk, a configured Slack app, and a local OpenAI-compatible chat-completions server at `http://localhost:1234/v1/chat/completions`.

```sh
python -m venv .venv
source .venv/bin/activate
pip install flask slackeventsapi slack-sdk splunk-sdk python-dotenv requests
```

Set `SIGNING_SECRET` and `SLACK_TOKEN` in your environment or a local `.env` file. Never commit credentials; `.env` is not currently ignored by this repository.

Before running, update the bot ID and Splunk connection/search settings in `main.py`. Replace the hardcoded Splunk credentials with secure configuration.

```sh
python main.py
```

The development server listens on port `8000`. Configure your Slack app's message event subscriptions and point its request URL to an externally reachable HTTPS endpoint forwarding to `/slack/events`.

## Prototype limitations

The Splunk search currently targets a fixed staging/EU index over the previous 15 days. The app runs in Flask debug mode and uses Slack's legacy `files_upload` method, which needs migration for current Slack deployments. This is not a production-ready service.

## Demo

- [Project overview](Slack%20Bot%20for%20On-call%20Assistance.pdf)
- [Video demo](LLMAssistBotForOnCall.mp4)
