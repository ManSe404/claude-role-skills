---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

We are about to sign off the data contract for the ERP orders feed, ./acme-pipeline/contracts/erp.yaml, with the ERP team. Does it describe what they actually send us? The deliveries are under ./acme-pipeline/sources/erp and the delivery log is ./acme-pipeline/ops/deliveries.jsonl. Do not change anything in the repository. Put any page you make under ./pages, and list the conflicts in your reply with their numbers. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
