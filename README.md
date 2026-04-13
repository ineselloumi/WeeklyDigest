# Weekly AI Adoption Gap Digest

A Claude-powered agent that searches the web every Monday for the latest news on the **AI adoption gap** (also called "capability overhang") and emails you a summary of the top 3 stories.

## What it does

- Runs automatically every Monday at 8 AM PST via GitHub Actions
- Uses Claude's web search to find the 3 most relevant stories from the past 7 days
- Emails you a formatted digest with headlines, summaries, sources, and links

## Fork and use it yourself

### 1. Fork this repo

Click **Fork** at the top right of this page.

### 2. Add your secrets

Go to your fork's **Settings → Secrets and variables → Actions** and add these 4 secrets:

| Secret | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `EMAIL_FROM` | Gmail address to send from |
| `EMAIL_TO` | Address to receive the digest |
| `EMAIL_APP_PASSWORD` | A [Gmail App Password](https://myaccount.google.com/apppasswords) (not your regular password) |

### 3. Test it

Go to **Actions → Weekly AI Adoption Gap Digest → Run workflow** to trigger a manual run and verify you receive the email.

The workflow will then run automatically every Monday.

## Customize it

To track a different topic, edit the `SYSTEM_PROMPT` and `USER_PROMPT` in `weekly_digest.py`.

To change the schedule, edit the cron expression in `.github/workflows/weekly_digest.yml`.
