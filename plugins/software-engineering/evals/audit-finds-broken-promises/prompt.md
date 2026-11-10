---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Go through the code of ./acme-index as it stands and find its bugs before we build more on it. Don't change anything. Put any page you make under ./pages, and list the findings in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
