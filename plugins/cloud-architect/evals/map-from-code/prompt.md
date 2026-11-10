---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Draw the cloud infrastructure of ./acme-cloud from its code, with what the internet can reach. There is no cloud login here and you must not use one. Do not ask me questions, assume where you must and say so. Do not change anything in the repository. Put any page you make under ./pages, and give me the main points in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
