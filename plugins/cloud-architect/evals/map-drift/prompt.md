---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Compare what is in ./acme-cloud with the export in ./acme-cloud/exports/az-resource-list-2026-11-08.json. What is in the code but not deployed, and what is deployed but not in the code? Do not ask me questions, assume where you must and say so. Put any page you make under ./pages, and give me the differences in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
