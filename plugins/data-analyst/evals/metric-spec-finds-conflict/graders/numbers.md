---
type: llm
---

The fixture has two definitions of net revenue. The finance one in models/marts/mart_net_revenue.sql gives EUR 85,390.00 for October on the sample; the BI one in reports/dashboards/revenue_dashboard.sql gives EUR 87,625.03. They differ by EUR 2,235.03, from a date basis (order date against shipped date), an added status (returned), a staff filter and the shipping fee.
PASS if the reply states both numbers (within EUR 0.05) or the gap of EUR 2,235.03, names at least two of those four differences, proposes one definition with its grain, filters, time window and an owner or a question for one, and prints no personal value.
FAIL if it invents a number, leaves the definition without what it excludes, or prints a personal value.
