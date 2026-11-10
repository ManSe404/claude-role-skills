---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Customer care asked us for a model that predicts which annual-plan customers will not renew, so they can email a reminder. The request is in ./acme-churn/docs/briefs/auto-renew-reminders.md. Should we build it? Do not change anything in the repository. Put any page you make under ./pages and summarise your answer in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
