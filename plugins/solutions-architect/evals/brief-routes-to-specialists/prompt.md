---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

A new client brief arrived: ./acme-solution/docs/briefs/claims-platform.md. It may cross several areas. Before anyone starts, work out which specialists we need and in what order, and write the calls to run next. Don't ask me questions, assume where you must and say so. Put any page you make under ./pages, and give me the plan in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
