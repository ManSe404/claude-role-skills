---
runs: 1
max_turns: 200
timeout_seconds: 3600
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

October has closed on the data platform in ./acme-pipeline. Run the platform-month chain and tell me what to stop, what to fix and who decides. Don't ask me questions. Change nothing in ./acme-pipeline. Put every page you make under ./pages, and say in your reply which steps ran and what each found. Shell commands cannot write files in this run, so write each page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
