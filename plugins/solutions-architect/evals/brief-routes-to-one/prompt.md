---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Another request came in: ./acme-solution/docs/briefs/room-booking.md. Work out which specialists we need for it and in what order, and write the calls to run next. Don't ask me questions, assume where you must and say so. Put any page you make under ./pages, and give me the plan in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
