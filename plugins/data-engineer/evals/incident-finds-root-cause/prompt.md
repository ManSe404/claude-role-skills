---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Finance says the sales numbers have not moved since Monday morning. Something in the nightly loads of ./acme-pipeline failed; the run records, check results, quarantine and the incident log are in ./acme-pipeline/ops. Find out what broke, why, and what we should do about it. Do not rerun any job. Do not change anything in the repository. Put any page you make under ./pages, and summarise what happened and what to do in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
