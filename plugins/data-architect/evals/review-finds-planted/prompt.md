---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Review the data platform in ./acme-data before we hand it over; sample exports are in ./acme-data/data. Don't change anything. Put any page you make under ./pages, and list the findings in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
