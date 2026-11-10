---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

We have three churn models scored on a holdout in ./acme-churn/data/predictions.csv: baseline_score is the current one, logreg_v2 and gbt_v7 are candidates. Which should we use? A false positive costs EUR 25 and a false negative EUR 90. Do not change anything in the repository. Put any page you make under ./pages and summarise your answer in your reply.
