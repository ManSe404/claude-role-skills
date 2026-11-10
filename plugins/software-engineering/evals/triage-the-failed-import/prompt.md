---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

The nightly order import of ./acme-orders has been failing since 2 October; the log is acme-orders/logs/acme-orders.log and the repository is ./acme-orders. Triage it now: how bad is it, what changed before it, what should we do, and draft the status update. Do not run or change anything, and do not post anywhere. Put any page you make under ./pages. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
