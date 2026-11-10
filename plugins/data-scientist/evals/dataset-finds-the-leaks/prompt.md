---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

We want to trust the churn model before we use it. The training and test sets are ./acme-churn/data/train.csv and ./acme-churn/data/test.csv, the modelling code is in ./acme-churn/model. Please audit the data and tell us what is wrong. Do not change anything in the repository. Put any page you make under ./pages and list the problems with their numbers in your reply.
