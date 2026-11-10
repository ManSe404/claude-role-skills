---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

The group wants the platform in ./acme-cloud-aws/docs/briefs/festival-platform.md and can put it on Azure or on AWS. Decide what it should run on, and compare what it would cost each month on each cloud. Use the saved price tables at ./acme-cloud-aws/prices/ and do not go online. Do not ask me questions, assume where you must and say so. Put any page you make under ./pages, and give me the decision and the two monthly totals in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
