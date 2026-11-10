---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

Net revenue at Acme Home Goods went from EUR 96,000.00 in September to EUR 85,390.00 in October, all rows loaded. How much of that is volume, how much mix and how much rate, by product line? The rows are in ./acme-sales/data/orders.csv (net_amount of completed orders by order_date, units as the volume). Put any page you make under ./pages and put the split in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
