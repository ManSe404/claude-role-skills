---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

In ./acme-orders I want pricing.order_total to take the VAT rate as a parameter, read from the settings (ACME_VAT_RATE), instead of the VAT_RATE constant. Before I touch anything: what does that change reach, and in what order should I make it? Put any page you make under ./pages, and give me the main points in your reply. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
