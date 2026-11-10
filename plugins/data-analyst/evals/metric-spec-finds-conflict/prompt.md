---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Finance and the BI dashboard report different October net revenue for Acme Home Goods, in ./acme-sales. Please look at how each one is computed and write the one definition we should all use, with what it does not include. The sample data is in ./acme-sales/data. Do not change anything in the repository. Put any page you make under ./pages, and state the numbers in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
