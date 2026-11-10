---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

We are about to build a churn model and nobody has looked at the data yet. The history is ./acme-churn/data/snapshots.csv, not split yet, the column to predict is churned_60d, which is decided 60 days after snapshot_date. Please explore it and tell us what relates to churn and what we should worry about before modelling. Do not change anything in the repository. Put any page you make under ./pages and list what you found with the numbers in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
