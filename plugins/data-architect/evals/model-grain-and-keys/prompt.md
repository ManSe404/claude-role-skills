---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Acme Foods wants a proper model of its sales, for revenue per store and per product per month and for repeat customers. The project is ./acme-data and sample exports are in ./acme-data/data. Don't ask me questions, assume where you must and say so. Put any page you make under ./pages, and summarise the model in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
