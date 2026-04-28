#!/usr/bin/env python3
"""
Weekly AI Adoption Gap news digest agent.

Searches the web for news about "AI adoption gap" / "capability overhang",
summarises the top 3 stories, and emails the digest.

Usage:
  python3 weekly_digest.py              # search + send email
  python3 weekly_digest.py --dry-run    # search only, print digest, no email

Required environment variables:
  ANTHROPIC_API_KEY   – Anthropic API key
  EMAIL_FROM          – sender Gmail address
  EMAIL_TO            – recipient address (can be the same as EMAIL_FROM)
  EMAIL_APP_PASSWORD  – Gmail App Password (not your regular Gmail password)
                        https://myaccount.google.com/apppasswords
"""

import os
import sys
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import anthropic

# ── Configuration ────────────────────────────────────────────────────────────

MODEL = "claude-sonnet-4-5"

SYSTEM_PROMPT = """\
You are a research assistant specialising in technology and AI policy news.

Your task: find and summarise the 3 most recent, insightful stories about the
"AI adoption gap" — the persistent gap between what AI systems can do and how
widely (or effectively) they are actually deployed in the real world. AI labs
sometimes call this "capability overhang".

Relevant angles include:
- Surveys or data on enterprise / consumer AI adoption rates
- Analysis of why AI capabilities outpace real-world deployment
- Commentary from researchers, labs, or policymakers on this gap
- Case studies of sectors slow to adopt AI despite clear benefits
- Economic or organisational barriers to AI adoption
- Personal adoption: individuals slow or reluctant to use AI tools in daily life
- Consumer-facing AI products and why everyday users don't engage with them
- Psychological, cultural, or accessibility barriers to personal AI use

When writing the digest:
- Focus on stories published in the past 7 days when possible
- Choose the 3 most newsworthy / insightful pieces
- Keep each summary factual and concise
- Highlight the "so what" for practitioners and researchers
"""

USER_PROMPT = """\
Search the web for the latest news (past 7 days) about the AI adoption gap \
and capability overhang in AI. Find the top 3 most relevant, recent stories. \
Consider both professional/enterprise adoption and personal/consumer adoption — \
if media coverage spans both, try to include at least one story from each lens.

Use at most 5 web searches total — be precise with your queries so you find \
the right articles quickly without over-searching.

IMPORTANT: You must include the full URL for every story. Do not omit or \
approximate links — use the exact URL returned by your web search results.

IMPORTANT: Your entire reply must be ONLY the digest below — no preamble, \
no commentary, no explanation before or after. Start your response with the \
word "Subject:" on the very first line.

Write the output as a plain-text weekly email digest in exactly this format:

Subject: Weekly AI Adoption Gap Digest – [Month Day, Year]

Hi,

Here are this week's top 3 stories on the AI adoption gap and capability overhang.

────────────────────────────────────
1. [HEADLINE]
   Source: [Publication] | [Date]
   Link: [full URL]

   [3-4 sentence summary]

   Why it matters: [1 sentence]

────────────────────────────────────
2. [HEADLINE]
   Source: [Publication] | [Date]
   Link: [full URL]

   [3-4 sentence summary]

   Why it matters: [1 sentence]

────────────────────────────────────
3. [HEADLINE]
   Source: [Publication] | [Date]
   Link: [full URL]

   [3-4 sentence summary]

   Why it matters: [1 sentence]

────────────────────────────────────

Until next week,
Your AI Digest Bot
"""

# ── Agent ────────────────────────────────────────────────────────────────────

def run_agent() -> str:
    """Run the news-search agent and return the digest text."""
    client = anthropic.Anthropic()

    tools = [{"type": "web_search_20260209", "name": "web_search"}]
    messages = [{"role": "user", "content": USER_PROMPT}]

    MAX_ITERATIONS = 15
    for iteration in range(MAX_ITERATIONS):
        print(f"  [iteration {iteration + 1}/{MAX_ITERATIONS}]", flush=True)
        # Retry up to 3 times on transient errors with exponential backoff.
        # We use streaming so the connection stays alive for long Opus responses
        # instead of hitting a read-timeout on a single blocking HTTP call.
        for attempt in range(3):
            try:
                with client.messages.stream(
                    model=MODEL,
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    tools=tools,
                    messages=messages,
                ) as stream:
                    # Drain all SSE events; get_final_message() accumulates them.
                    for _ in stream:
                        pass
                    response = stream.get_final_message()
                break
            except (anthropic.RateLimitError, anthropic.APITimeoutError) as e:
                if attempt == 2:
                    raise
                wait = 60 * (attempt + 1)
                label = "rate limit" if isinstance(e, anthropic.RateLimitError) else "timeout"
                print(f"  [{label}] waiting {wait}s before retry …", flush=True)
                time.sleep(wait)

        # Print live progress so you can watch the agent work
        for block in response.content:
            btype = getattr(block, "type", None)
            if btype in ("tool_use", "server_tool_use"):
                if getattr(block, "name", "") == "web_search":
                    query = (getattr(block, "input", None) or {}).get("query", "")
                    print(f"  [search] {query}", flush=True)
            elif btype == "web_search_tool_result":
                n = len(getattr(block, "content", []))
                print(f"  [results] {n} result(s) returned", flush=True)
            elif btype == "text":
                snippet = block.text.strip().replace("\n", " ")[:120]
                if snippet:
                    print(f"  [agent] {snippet}", flush=True)

        # Append the assistant turn
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # Join all text blocks from the final response.
            full_text = "".join(b.text for b in response.content if hasattr(b, "text"))
            full_text = full_text.replace("**", "").strip()

            # Try to find the "Subject:" header in the final response.
            idx = full_text.find("Subject:")
            if idx != -1:
                return full_text[idx:]

            # Fallback: search across ALL accumulated assistant turns —
            # the model may have written the digest in an earlier pass.
            all_text = ""
            for msg in messages:
                if msg["role"] == "assistant":
                    content = msg["content"]
                    if isinstance(content, list):
                        for block in content:
                            if hasattr(block, "text"):
                                all_text += block.text
            all_text = all_text.replace("**", "")
            idx = all_text.find("Subject:")
            if idx != -1:
                return all_text[idx:]

            # Last resort: if we have substantial text, prepend a Subject line
            # so the rest of the pipeline (email sender) still works.
            if len(full_text) > 200:
                import datetime
                today = datetime.date.today().strftime("%B %d, %Y")
                header = f"Subject: Weekly AI Adoption Gap Digest – {today}\n\n"
                return header + full_text

            raise RuntimeError("end_turn reached but no digest found")

        if response.stop_reason == "pause_turn":
            # Server-side tool loop hit its limit; re-send to continue
            print("  [pause_turn] continuing …", flush=True)
            continue

        if response.stop_reason == "tool_use":
            # web_search_20260209 is a server-side tool: the API executes the
            # search and embeds the results as web_search_tool_result blocks
            # inside response.content. We must NOT send extra tool_result
            # messages back — just loop so the model can read its own results.
            continue

        # Unexpected stop reason – bail out with whatever text we have
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        raise RuntimeError(f"Unexpected stop_reason: {response.stop_reason}")

    raise RuntimeError("Agent exceeded maximum iterations without finishing")


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(body: str) -> None:
    sender = os.environ["EMAIL_FROM"]
    recipient = os.environ["EMAIL_TO"]
    password = os.environ["EMAIL_APP_PASSWORD"]

    # Pull the subject line out of the body if present
    subject = "Weekly AI Adoption Gap Digest"
    lines = body.strip().splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if line.lower().startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
            body_start = i + 1
            break
    email_body = "\n".join(lines[body_start:]).strip()

    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(email_body, "plain"))

    print(f"Sending email to {recipient} …")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())
    print("Email sent successfully.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    dry_run = "--dry-run" in sys.argv

    # Validate required env vars
    missing = [v for v in ["ANTHROPIC_API_KEY"] if not os.getenv(v)]
    if not dry_run:
        missing += [v for v in ["EMAIL_FROM", "EMAIL_TO", "EMAIL_APP_PASSWORD"]
                    if not os.getenv(v)]
    if missing:
        print(f"Error: missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    print("Running news agent …", flush=True)
    digest = run_agent()

    print("\n" + "=" * 64)
    print("DIGEST:")
    print("=" * 64)
    print(digest)
    print("=" * 64 + "\n")

    if dry_run:
        print("[DRY RUN] Email not sent.")
    else:
        send_email(digest)


if __name__ == "__main__":
    main()
