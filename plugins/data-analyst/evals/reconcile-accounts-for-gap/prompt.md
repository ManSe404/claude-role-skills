---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

The ERP says October net revenue was EUR 85,390.00 and the finance ledger says less. The close cannot be signed until someone explains the whole difference. The files are ./acme-sales/data/orders.csv (completed orders by order_ts, net_amount) and ./acme-sales/data/ledger.csv (amount by posted_at), joined on order_id. Put any page you make under ./pages and state how the difference is made up in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
