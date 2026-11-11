---
runs: 1
max_turns: 200
timeout_seconds: 3600
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Marketing wants a model that predicts which customers of Acme Stream will churn; the data is in ./acme-churn/data and the label is churned. Run the model-build chain and tell me ship, do not ship or inconclusive. Don't ask me questions. Change nothing in ./acme-churn. Put every page you make under ./pages, and say in your reply which steps ran and what each found. Shell commands cannot write files in this run, so write each page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
