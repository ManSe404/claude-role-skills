---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

The CRM vendor has started sending us daily exports for Acme Foods. The last two deliveries are in ./acme-pipeline/sources/crm/2026-11-03 and ./acme-pipeline/sources/crm/2026-11-04, and the vendor's document is ./acme-pipeline/sources/crm/README-vendor.md. Before anyone writes a contract or a loader for it: what are we really getting, and where does it differ from what the vendor promises? Do not change anything in the repository. Put any page you make under ./pages, and list what you found in your reply with the counts. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
