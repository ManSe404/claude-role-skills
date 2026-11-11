---
runs: 1
max_turns: 200
timeout_seconds: 3600
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Take over ./acme-orders: we must own this repository from now on. Run the whole take-over chain and tell me what was found and whether the chain is done. Don't ask me questions. Change nothing in ./acme-orders. Put every page you make under ./pages, and say in your reply which steps ran and what each found. Shell commands cannot write files in this run, so write each page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
