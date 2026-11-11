---
runs: 1
max_turns: 200
timeout_seconds: 3600
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

The client brief is ./acme-solution/docs/briefs/claims-platform.md. Run the new-solution chain from the brief to the reviewed solution and tell me whether it holds together. Don't ask me questions. Change nothing in ./acme-solution. Put every page you make under ./pages, and say in your reply which steps ran and what each found. Shell commands cannot write files in this run, so write each page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
