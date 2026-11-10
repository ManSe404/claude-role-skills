---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Please read out the renewal-nudge A/B test. ./acme-churn/docs/briefs/renewal-nudge-experiment.md says what was run; the two files are ./acme-churn/data/experiment_broken.csv and ./acme-churn/data/experiment_clean.csv. Should we ship it? Do not change anything in the repository. Put any page you make under ./pages and summarise your answer in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
