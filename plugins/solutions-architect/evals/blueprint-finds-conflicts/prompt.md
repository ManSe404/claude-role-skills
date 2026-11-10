---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

The specialists have written their pages for the claims platform in ./acme-solution/pages, and the client brief is ./acme-solution/docs/briefs/claims-platform.md. Join them into one solution and tell me what contradicts. Don't ask me questions. Change nothing in ./acme-solution. Put any page you make under ./pages, and list the conflicts in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
