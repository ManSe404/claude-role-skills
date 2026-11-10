---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Before Monday's management meeting I need to know which tables of ./acme-pipeline we can trust right now, and whether our checks are worth anything. The check results, the quarantine and the run records are in ./acme-pipeline/ops; the checks are defined in ./acme-pipeline/checks. Do not change anything in the repository. Put any page you make under ./pages, and give your answer per table in your reply, with the numbers behind it. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
