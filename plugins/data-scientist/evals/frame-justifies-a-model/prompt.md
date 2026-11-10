---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

The retention team wants a churn prediction to choose who gets a retention offer. The brief is in ./acme-churn/docs/briefs/retention-offers.md. What should we build, what must it beat, and how will we know it is good enough? Do not change anything in the repository. Put any page you make under ./pages and summarise your answer in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
