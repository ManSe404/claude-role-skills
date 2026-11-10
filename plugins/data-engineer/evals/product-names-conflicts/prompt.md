---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

More teams are about to start reading gold.sales_daily from ./acme-pipeline. Write the guide a consumer of that table needs, and tell us what in its documents is wrong or missing before we open it up. A sample of the table is under ./acme-pipeline/samples. Do not change anything in the repository. Put any page you make under ./pages, and list the problems in your reply with their numbers. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
