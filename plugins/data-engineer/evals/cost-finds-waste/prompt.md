---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

The bill of our data platform in ./acme-pipeline keeps growing, and finance wants to know where the money goes and what we can cut. The billing export, the table sizes, the query log and the run records are in ./acme-pipeline/ops. Do not change anything in the repository. Put any page you make under ./pages, and list in your reply what to cut, with the money each cut saves a month. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
