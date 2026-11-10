---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Review the changes in ./acme-orders since the last deploy, d22ee8f..HEAD, before we deploy them again. Don't change anything in the repo and don't post anywhere. Give me the findings and the verdict in your reply. Put any page you make under ./pages. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
