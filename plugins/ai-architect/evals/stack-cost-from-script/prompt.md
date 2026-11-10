---
runs: 1
max_turns: 80
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write]
---

The pattern for Acme's support assistant (./acme-assist/docs/briefs/support-v2.md) is decided: a routed workflow. A small model classifies each question; how-to questions go to retrieval over the manuals and a large model writes the answer; order status is a live read-only call to the OrderDesk API; returns go to the support staff. Pick the stack and tell me what it costs per month at their volume. I have no price table yet and you must not go online. Put any page you make under ./pages. Shell commands cannot write files in this run, so write the page's JSON under ./pages with the Write tool, check it with render_page.py --check, and do not save the HTML or mention that it is missing.
