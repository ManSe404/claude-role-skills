# Acme Home Goods sales analytics

Small analytics project of Acme Home Goods: a home-goods retailer with a web shop and six stores.
It holds the dbt models and the reports the finance and BI teams work from. Everything here is
fictional.

- `models/`: dbt models on top of the ERP extract (`analytics.orders`).
- `reports/dashboards/`: SQL behind the BI dashboards.
- `reports/october_review/`: the October sales review for the leadership team.
- `docs/questions/`: questions the business has asked about these numbers.
- `data/` (not committed): sample extracts of the ERP, the finance ledger and the web sessions.

Finance owns `net_revenue` in the model `mart_net_revenue`. The BI team keeps its own version for
the dashboard.
