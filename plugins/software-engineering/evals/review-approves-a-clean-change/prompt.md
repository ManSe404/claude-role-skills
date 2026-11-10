---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Review commit 7a9f245 in ./acme-orders ("pricing: round once per order, not per line"), the range 7a9f245^..7a9f245, before it goes out. Don't change anything. Give me the verdict and what looks good in your reply. Put any page you make under ./pages. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
