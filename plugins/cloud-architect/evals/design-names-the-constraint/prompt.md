---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Here is the next platform: ./acme-cloud/docs/briefs/festival-platform.md. Where should it run on Azure and what will it cost each month? Use the saved price table at ./acme-cloud/prices/azure-retail-2026-11-10.json and do not go online. Do not ask me questions, assume where you must and say so. Put any page you make under ./pages, and give me the decision and its binding constraint in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
