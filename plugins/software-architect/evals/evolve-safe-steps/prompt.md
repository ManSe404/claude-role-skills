---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

We want to make Billing in ./acme-logistics a module we can release on its own. Plan how to get there without stopping the system. Don't ask me questions, assume where you must and say so. Don't change anything. Put any page you make under ./pages, and give me the plan in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
