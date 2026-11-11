---
runs: 1
max_turns: 200
timeout_seconds: 3600
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

The daily import of ./acme-orders has been failing since 06:00; the log is ./acme-orders/logs/acme-orders.log. Run the incident chain from triage to the write-up and tell me whether the incident is closed. Don't ask me questions. Change nothing in ./acme-orders. Put every page you make under ./pages, and say in your reply which steps ran and what each found. Shell commands cannot write files in this run, so write each page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
