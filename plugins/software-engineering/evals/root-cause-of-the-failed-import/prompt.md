---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

The nightly order import of ./acme-orders has failed since 2 October. The log is acme-orders/logs/acme-orders.log. Find out why. Put any page you make under ./pages, and give me the main points in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
