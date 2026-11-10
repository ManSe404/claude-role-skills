---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

We have to move the old cron estate in ./acme-pipeline/legacy onto the new platform. Tell us which jobs to keep, rebuild or retire, and plan the move in waves we can check and roll back. Do not change anything in the repository. Put any page you make under ./pages, and in your reply list what you found in the estate and the waves. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
