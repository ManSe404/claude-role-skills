"""The git history of the acme-sales fixture.

The files under files/ are the state after the last commit. Each commit lists the files it adds and the edits it
makes, as (path, before, after); the builder undoes the edits backwards to recover each earlier state.

The story: Acme Home Goods keeps a small dbt project and report folder. Finance defined net revenue in August, the BI
team built its own version for the dashboard, and in mid-October the BI team changed which orders its number counts.
In November an analyst wrote the October review. Everything here is fictional.
"""

MILENA = ("Milena Hrast", "milena.hrast@example.com")
RADE = ("Rade Lipovac", "rade.lipovac@example.com")

COMMITS = [
    {
        "date": "2026-08-11T09:30:00+02:00",
        "author": RADE,
        "message": "Start the analytics project: staging for orders and finance net revenue",
        "add": [
            ".gitignore",
            "README.md",
            "dbt_project.yml",
            "models/sources.yml",
            "models/staging/stg_orders.sql",
            "models/marts/mart_net_revenue.sql",
            "models/marts/schema.yml",
        ],
    },
    {
        "date": "2026-09-02T11:10:00+02:00",
        "author": MILENA,
        "message": "BI dashboard: monthly revenue from staging",
        "add": ["reports/dashboards/revenue_dashboard.sql"],
    },
    {
        "date": "2026-10-14T16:20:00+02:00",
        "author": MILENA,
        "message": "BI dashboard: leave out staff orders",
        "edit": [
            (
                "reports/dashboards/revenue_dashboard.sql",
                "where status in ('completed', 'returned')\n",
                "where status in ('completed', 'returned')\n  and channel <> 'staff'\n",
            ),
        ],
    },
    {
        "date": "2026-11-05T10:45:00+01:00",
        "author": MILENA,
        "message": "October review: queries, report and numbers",
        "add": [
            "reports/october_review/report.md",
            "reports/october_review/revenue_by_line.sql",
            "reports/october_review/revenue_by_region.sql",
            "reports/october_review/sep_vs_oct.sql",
            "reports/october_review/conversion.sql",
            "reports/october_review/conversion_by_device.sql",
            "reports/october_review/avg_order_by_store.sql",
            "reports/october_review/orders_by_status.sql",
            "reports/october_review/monthly_chart.ipynb",
            "reports/october_review/output/revenue_by_line.csv",
            "reports/october_review/output/revenue_by_region.csv",
            "reports/october_review/output/sep_vs_oct.csv",
            "reports/october_review/output/conversion.csv",
            "reports/october_review/output/conversion_by_device.csv",
            "reports/october_review/output/avg_order_by_store.csv",
            "reports/october_review/output/orders_by_status.csv",
        ],
    },
    {
        "date": "2026-11-06T09:05:00+01:00",
        "author": RADE,
        "message": "Questions from the business about the October numbers",
        "add": [
            "docs/questions/metric-spec.md",
            "docs/questions/number-moved.md",
            "docs/questions/number-reconcile.md",
            "docs/questions/report-review.md",
        ],
    },
]
