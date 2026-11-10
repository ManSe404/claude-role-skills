---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Draw the system in ./acme-logistics so I can explain it to a new colleague: who uses it, what runs, and what is inside the part that matters most. Put the page under ./pages and tell me how to open it. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
