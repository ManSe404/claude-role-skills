---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

I just inherited the repository in ./acme-orders and nobody can explain it to me. Map it for me: what it does, how it starts, how the code fits together, what it talks to. Put any page you make under ./pages, and give me the main points in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
