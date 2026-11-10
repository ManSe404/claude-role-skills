---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Please check the October review in ./acme-sales/reports/october_review before it goes to the leadership team on Friday. The sample data is in ./acme-sales/data. Do not change anything in the repository. Put any page you make under ./pages, and list what is wrong in your reply with the corrected numbers where you can compute them. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
