---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

The README of ./acme-orders may be out of date. Tell me what the code exposes that the README does not say, and what the README says that the code no longer has, then draft a corrected Run section. Do not write into the repository. Put any page you make under ./pages. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
