---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Acme sent another request: ./acme-assist/docs/briefs/email-tagging.md. What should we build for it? Don't ask me questions, assume where you must and say so. Put any page you make under ./pages, and give me the decision in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
